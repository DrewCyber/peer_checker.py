### Yggdrasil peer checker / peer_checker.py
No git binnary is required.  
No cloned ["public_peers"](https://github.com/yggdrasil-network/public-peers) repository is required.  
Only 1 python script with config inside.  

### Requirements
Linux, python 3.9+ (tested on 3.9.19)

### Installation
```
pip3 install aioquic, dulwich websockets
```
or
```
pip3 install -r requirements.txt
```

### Usage
```
usage: peer_checker.py [-h] [-r REGIONS [REGIONS ...]] [-c COUNTRIES [COUNTRIES ...]] [-d] [-p] [-m MAX_CONCURRENCY] [-n NUMBER] [--tcp] [--tls]
                       [--quic] [--ws] [--wss]
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
  --tcp                 show tcp peers
  --tls                 show tls peers
  --quic                show quic peers
  --ws                  show ws peers
  --wss                 show wss peers
```