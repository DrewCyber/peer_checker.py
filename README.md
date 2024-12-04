### Yggdrasil peer checker / peer_checker.py
Support tcp, tls, quic, ws, wss peers.  
No git binnary is required.  
No cloned ["public_peers"](https://github.com/yggdrasil-network/public-peers) repository is required.  
Only 1 python script with config inside.  

### Requirements
Linux, python 3.9+ (tested on 3.9.19)

### Installation
```
python3 -m ensurepip
pip3 install aioquic dulwich websockets
curl -L https://raw.githubusercontent.com/DrewCyber/peer_checker.py/refs/heads/master/peer_checker.py > peer_checker.py
chmod a+x peer_checker.py
```

### Usage
```
usage: peer_checker.py [-h] [-r REGIONS [REGIONS ...]] [-c COUNTRIES [COUNTRIES ...]] [-d] [-p] [-m MAX_CONCURRENCY] [-n NUMBER] [-q] [--tcp]
                       [--tls] [--quic] [--ws] [--wss]
                       [data_dir]

positional arguments:
  data_dir              path to public peers repository

options:
  -h, --help            show this help message and exit
  -r, --regions REGIONS [REGIONS ...]
                        list of peers regions
  -c, --countries COUNTRIES [COUNTRIES ...]
                        list of peers countries
  -d, --show_dead       show dead peers table
  -p, --do_not_pull     don't pull new peers data from git repository on start
  -m, --max_concurrency MAX_CONCURRENCY
                        maximum number of concurrent connections (default: 10)
  -n, --number NUMBER   number of peers to filter
  -q, --quiet           print only peers uri (for yggdrasil.conf)
  --tcp                 show tcp peers
  --tls                 show tls peers
  --quic                show quic peers
  --ws                  show ws peers
  --wss                 show wss peers
```

### Known issue

BUG: It takes 60 seconds to check QUIC dead peers with aioquic.asyncio.connect  
There is no timeout parameter for aioquic.asyncio.connect  
If we use asyncio.wait_for as a timeout, we will get "ERROR:asyncio:Future exception was never retrieved"