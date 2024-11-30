#!/usr/bin/env python3
import re
import os
import sys
import logging
import asyncio
import subprocess
import configparser
import argparse
from datetime import datetime, timezone
import websockets
import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration

get_loop = asyncio.get_running_loop if hasattr(asyncio, "get_running_loop") \
    else asyncio.get_event_loop

def get_peers(regions, countries):
    """Scan repository directory for peers"""
    assert os.path.exists(os.path.join(DATA_DIR, "README.md")), "Invalid path"
    peers = []

    if not regions:
        regions = [d for d in os.listdir(DATA_DIR) if \
                   os.path.isdir(os.path.join(DATA_DIR, d)) and \
                   not d in [".git", "other"]]
    if not countries:
        for region in regions:
            r_path = os.path.join(DATA_DIR, region)
            countries += [f for f in os.listdir(r_path) if f.endswith(".md")]
    else:
        countries = [country + ".md" for country in countries]

    for region in regions:
        for country in countries:
            cfile = os.path.join(DATA_DIR, region, country)
            if os.path.exists(cfile):
                with open(cfile, encoding="utf-8") as f:
                    for p in PEER_REGEX.findall(f.read()):
                        peers.append(
                            {"uri": p, "region": region, "country": country})
    return peers

async def resolve(name):
    """Get IP address or none to skip scan"""
    # handle clear ipv6 address
    if name.startswith("["):
        return name[1:-1]

    try:
        info = await get_loop().getaddrinfo(name, None)
        addr = info[0][4][0]
    except Exception as e:
        logging.debug("Resolve error %s: %s", type(e), e)
        addr = None

    return addr

async def isup(peer, semaphore):
    """Check if peer is up and measure latency"""
    peer["up"] = False
    peer["latency"] = None
    addr = await resolve(peer["uri"][1])
    async with semaphore:
        if addr:
            proto = peer["uri"][0]
            if proto == "wss":
                url = f"wss://{peer['uri'][1]}:{peer['uri'][2]}"
                start_time = datetime.now()
                try:
                    async with websockets.connect(url) as websocket:
                        peer["latency"] = datetime.now() - start_time
                        peer["up"] = True
                except Exception as e:
                    logging.debug("WSS connection error %s: %s", type(e), e)
            elif proto == "ws":
                url = f"ws://{addr}:{peer['uri'][2]}"
                start_time = datetime.now()
                try:
                    async with websockets.connect(url) as websocket:
                        peer["latency"] = datetime.now() - start_time
                        peer["up"] = True
                except Exception as e:
                    logging.debug("WS connection error %s: %s", type(e), e)
            elif proto == "quic":
                configuration = QuicConfiguration(is_client=True)
                configuration.verify_mode = False  # Equivalent to InsecureSkipVerify
                configuration.timeout = 1
                start_time = datetime.now()
                try:
                    #BUG: It takes 60 seconds to check dead peers with aioquic.asyncio.connect
                    #There is no timeout parameter for aioquic.asyncio.connect
                    #If we use asyncio.wait_for as a timeout, we will get "ERROR:asyncio:Future exception was never retrieved"
                    async def connect_and_check():
                        async with aioquic.asyncio.connect(addr, peer["uri"][2], configuration=configuration) as quic_stream:
                            peer["latency"] = datetime.now() - start_time
                            peer["up"] = True
                    await asyncio.wait_for(connect_and_check(), timeout=61)
                except Exception as e:
                    logging.debug("QUIC connection error %s: %s", type(e), e)
            else:
                start_time = datetime.now()
                try:
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(
                            addr, peer["uri"][2]), 5)
                    peer["latency"] = datetime.now() - start_time
                    writer.close()
                    await writer.wait_closed()
                    peer["up"] = True
                except Exception as e:
                    logging.debug("Connection error %s: %s", type(e), e)

        return peer

def print_results(results):
    """Output results"""
    def prepare_table(peer_list_iter):
        """Prepare peers table for print"""
        addr_width = 0
        peers_table = []
        for p in peer_list_iter:
            addr = "{}://{}:{}".format(*p["uri"])
            latency = None
            if p["latency"] is not None:
                latency = round(p["latency"].total_seconds() * 1000, 3)
            place = "{}/{}".format(p["region"], p["country"])
            peers_table.append((addr, latency, place))
            # store max addr width
            if len(addr) > addr_width:
                addr_width = len(addr)
        return peers_table, addr_width

    print("\n=================================")
    print(" ALIVE PEERS (sorted by latency):")
    print("=================================")
    p_table, addr_w = prepare_table(filter(lambda p: p["up"], results))
    print("URI".ljust(addr_w), "Latency (ms)", "Location")
    print("---".ljust(addr_w), "------------", "--------")
    for p in sorted(p_table, key=lambda x: x[1]):
        print(p[0].ljust(addr_w), repr(p[1]).ljust(12), p[2])

    if SHOW_DEAD:
        print("\n============")
        print(" DEAD PEERS:")
        print("============")
        p_table, addr_w = prepare_table(filter(lambda p: not p["up"], results))
        print("URI".ljust(addr_w), "Location")
        print("---".ljust(addr_w), "--------")
        for p in p_table:
            print(p[0].ljust(addr_w), p[2])

async def main(peers, max_concurrency):
    semaphore = asyncio.Semaphore(max_concurrency)
    results = await asyncio.gather(*[isup(p, semaphore) for p in peers])
    return results


if __name__ == "__main__":
    # load config file
    cfg = configparser.ConfigParser()
    cfg.read("peer_checker.conf")
    config = cfg["CONFIG"]

    # get arguments from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('data_dir', nargs='?', type=str,
                        help='path to public peers repository')
    parser.add_argument('-r', '--regions',
                        action="extend", nargs="+", type=str,
                        help='list of peers regions')
    parser.add_argument('-c', '--countries',
                        action="extend", nargs="+", type=str,
                        help='list of peers countries')
    parser.add_argument('-d', '--show_dead', action='store_true', default=None,
                        help='show dead peers table')
    parser.add_argument('-p', '--do_not_pull',
                        action='store_false', default=None,
                        help="don't pull new peers data from git repository "
                             "on start")
    parser.add_argument('-m', '--max_concurrency',
                        action="store", type=int, default=10,
                        help='maximum number of concurrent connections (default: 10)')
    parser.add_argument('--tcp', action='store_true', default=None,
                        help='show tcp peers')
    parser.add_argument('--tls', action='store_true', default=None,
                        help='show tls peers')
    parser.add_argument('--quic', action='store_true', default=None,
                        help='show quic peers')
    parser.add_argument('--ws', action='store_true', default=None,
                        help='show ws peers')
    parser.add_argument('--wss', action='store_true', default=None,
                        help='show wss peers')
    args = parser.parse_args()

    # command line args replace config options
    DATA_DIR = args.data_dir if args.data_dir is not None else \
        config.get("data_dir", fallback="public_peers")
    SHOW_DEAD = args.show_dead if args.show_dead is not None else \
        config.getboolean("show_dead", fallback=False)
    UPD_REPO = args.do_not_pull if args.do_not_pull is not None else \
        config.getboolean("update_repo", fallback=True)
    MAX_CONCURRENCY = args.max_concurrency if args.max_concurrency is not None else \
        config.getint("max_concurrency", fallback=10)

    peer_kind = ''
    if args.tcp is not None:
        peer_kind += "tcp|"
    if args.tls is not None:
        peer_kind += "tls|"
    if args.quic is not None:
        peer_kind += "quic|"
    if args.ws is not None:
        peer_kind += "ws|"
    if args.wss is not None:
        peer_kind += "wss|"
    if peer_kind == '':
        peer_kind = config.get("peer_kind")
        if peer_kind not in ("tcp", "tls", "quic", "ws", "wss"):
            peer_kind = "tcp|tls|quic|ws|wss"
    else:
        peer_kind = peer_kind[:-1]
    PEER_REGEX = re.compile(rf"`({peer_kind})://([a-z0-9\.\-\:\[\]]+):([0-9]+)`")

    regions = args.regions if args.regions is not None else \
        config.get("regions_list", fallback='').split()
    countries = args.countries if args.countries is not None else \
        config.get("countries_list", fallback='').split()

    # get or update public peers data from git
    if not os.path.exists(DATA_DIR):
        subprocess.call(
            ["git", "clone", "--depth=1", config.get("repo_url"), DATA_DIR])
    elif UPD_REPO and os.path.exists(os.path.join(DATA_DIR, ".git")):
        print("Update public peers repository:")
        subprocess.call(["git", "-C", DATA_DIR, "pull"])

    # parse and check peers
    try:
        peers = get_peers(regions, countries)
    except:
        print(f"Can't find peers in a directory: {DATA_DIR}")
        sys.exit()

    print("\nReport date (UTC):", datetime.now(timezone.utc).strftime("%c"))
    print_results(asyncio.run(main(peers,MAX_CONCURRENCY)))
