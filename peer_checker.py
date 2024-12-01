#!/usr/bin/env python3
import re
import os
import sys
import logging
import asyncio
import subprocess
import shlex
import argparse
from datetime import datetime, timezone
import websockets
import aioquic.asyncio
from aioquic.quic.configuration import QuicConfiguration
from dulwich import porcelain

# Defaults
DATA_DIR            = "public_peers"    # Path where data will be stored. It can be relative.
REPO_URL            = "https://github.com/yggdrasil-network/public-peers.git"
NUMBER              = ""                # The number of peers to filter
UPDATE_REPO         = True              # Pull new data from git repository on start
SHOW_DEAD           = False             # Show dead peers table
REGIONS_LIST        = ""                # africa, asia, australia, europe, mena, north-america, other, south-america
COUNTRIES_LIST      = ""                # List of countries to test peers from
MAX_CONCURRENCY     = ""                # Maximum number of concurrent connections (default: 10)
QUIET               = False             # Print only peers uri (for yggdrasil.conf)
DEFAULT_PEER_KIND   = ""                # Peers types: tcp, tls, quic, ws, wss. Check all if empty

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

def qprint(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)

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
            qprint (f"Checking {peer['uri'][1]}:{peer['uri'][2]}")
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

def print_results(results, limit):
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

    qprint("\n=================================")
    qprint(" ALIVE PEERS sorted by latency (highest to lowest):")
    qprint("=================================")
    p_table, addr_w = prepare_table(filter(lambda p: p["up"], results))
    qprint("URI".ljust(addr_w), "Latency (ms)", "Location")
    qprint("---".ljust(addr_w), "------------", "--------")
    if limit is not None:
        limit = -limit  # reverce limit with reverse order
    for i,p in enumerate(sorted(p_table, key=lambda x: x[1], reverse=True)[limit:]):
        if QUIET:
            # Print only URIs
            # Add a comma only if it's not the last element
            table_len = len(p_table) - 1 if limit is None else -limit - 1
            print('"' + p[0] + '"' + ("," if i < table_len else ""))
        else:
            # Print URI, latency and location
            print(p[0].ljust(addr_w), repr(p[1]).ljust(12), p[2])

    if SHOW_DEAD:
        qprint("\n============")
        qprint(" DEAD PEERS:")
        qprint("============")
        p_table, addr_w = prepare_table(filter(lambda p: not p["up"], results))
        qprint("URI".ljust(addr_w), "Location")
        qprint("---".ljust(addr_w), "--------")
        for p in p_table:
            qprint(p[0].ljust(addr_w), p[2])

async def main(peers, max_concurrency):
    semaphore = asyncio.Semaphore(max_concurrency)
    results = await asyncio.gather(*[isup(p, semaphore) for p in peers])
    return results


if __name__ == "__main__":
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
                        action="store", type=int, default=None,
                        help='maximum number of concurrent connections (default: 10)')
    parser.add_argument('-n', '--number',
                        action="store", type=int, default=None,
                        help='number of peers to filter')
    parser.add_argument('-q', '--quiet', action='store_true', default=None,
                        help='print only peers uri (for yggdrasil.conf)')
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
    DATA_DIR = args.data_dir if args.data_dir is not None else DATA_DIR
    SHOW_DEAD = args.show_dead if args.show_dead is not None else bool(SHOW_DEAD)
    UPDATE_REPO = args.do_not_pull if args.do_not_pull is not None else bool(UPDATE_REPO)
    MAX_CONCURRENCY = args.max_concurrency or (int(MAX_CONCURRENCY) if MAX_CONCURRENCY.strip() else 10)
    NUMBER = args.number or (int(NUMBER) if NUMBER.strip() else None)
    QUIET = args.quiet if args.quiet is not None else bool(QUIET)

    peer_kind = ''
    # Get values from defaults config
    if DEFAULT_PEER_KIND != "":
        kinds = shlex.split(DEFAULT_PEER_KIND.replace(",", " "))
        peer_kind = "|".join([kind for kind in kinds])
    # Override kind from command line
    cli_peer_kind = ''
    if args.tcp is not None:
        cli_peer_kind += "tcp|"
    if args.tls is not None:
        cli_peer_kind += "tls|"
    if args.quic is not None:
        cli_peer_kind += "quic|"
    if args.ws is not None:
        cli_peer_kind += "ws|"
    if args.wss is not None:
        cli_peer_kind += "wss|"
    if cli_peer_kind != "":
        peer_kind = cli_peer_kind[:-1]
    # Check all kinds if none specified
    if peer_kind == "":
        peer_kind = "tcp|tls|quic|ws|wss"

    PEER_REGEX = re.compile(rf"`({peer_kind})://([a-z0-9\.\-\:\[\]]+):([0-9]+)`")
    regions = args.regions if args.regions is not None else shlex.split(REGIONS_LIST.replace(",", " "))
    countries = args.countries if args.countries is not None else shlex.split(COUNTRIES_LIST.replace(",", " "))

    # get or update public peers data from git
    if not os.path.exists(DATA_DIR):
        porcelain.clone(REPO_URL, DATA_DIR, depth=1)
    elif UPDATE_REPO and os.path.exists(os.path.join(DATA_DIR, ".git")):
        print("Update public peers repository:")
        porcelain.pull(DATA_DIR, REPO_URL)

    # parse and check peers
    try:
        peers = get_peers(regions, countries)
    except:
        print(f"Can't find peers in a directory: {DATA_DIR}")
        sys.exit()

    qprint("\nReport date (UTC):", datetime.now(timezone.utc).strftime("%c"))
    qprint ("Total peers count:", len(peers))
    print_results(asyncio.run(main(peers,MAX_CONCURRENCY)), NUMBER)
