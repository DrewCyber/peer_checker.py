### Yggdrasil peer checker / peer_checker.py
Support tcp, tls, quic, ws, wss peers.  
No git binnary is required.  
No cloned ["public_peers"](https://github.com/yggdrasil-network/public-peers) repository is required.  
Only 1 python script with config inside.  

### Requirements
Linux, python 3.9+ (tested on 3.9.19)  
Tested on Windows 10 x64, version 21H2 pro (with auto-py-to-exe)  

### Installation
<details><summary>with pyenv</summary>
  
```
eval "$(pyenv init -)"
```
</details>
  
```
python3 -m ensurepip
pip3 install aioquic dulwich websockets
curl -L https://raw.githubusercontent.com/DrewCyber/peer_checker.py/refs/heads/master/peer_checker.py > peer_checker.py
chmod a+x peer_checker.py
```

### Usage
```
usage: peer_checker.py [-h] [-r REGIONS [REGIONS ...]] [-c COUNTRIES [COUNTRIES ...]] [-d] [-p] [-m MAX_CONCURRENCY] [-u] [-n NUMBER] [-q] [--tcp]
                       [--tls] [--quic] [--ws] [--wss]
                       [data_dir]

positional arguments:
  data_dir              path to public peers repository

options:
  -h, --help            show this help message and exit
  -r REGIONS [REGIONS ...], --regions REGIONS [REGIONS ...]
                        list of peers regions
  -c COUNTRIES [COUNTRIES ...], --countries COUNTRIES [COUNTRIES ...]
                        list of peers countries
  -d, --show_dead       show dead peers table
  -p, --do_not_pull     don't pull new peers data from git repository on start
  -m MAX_CONCURRENCY, --max_concurrency MAX_CONCURRENCY
                        maximum number of concurrent connections (default: 10)
  -u, --unique          show only best peer per ip address
  -n NUMBER, --number NUMBER
                        number of peers to filter
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

### TODO:
 - Need to ignore/handle cloudflare ips (https://www.cloudflare.com/ips-v4/#)
 - Need to show key if it's required for the peer connection.
```
tcp://ip6.fvm.mywire.org:8080?key=000000000143db657d1d6f80b5066dd109a4cb31f7dc6cb5d56050fffb014217
```