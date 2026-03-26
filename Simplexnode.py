#!/usr/bin/env python3
"""
Quantum Simplex Blockchain – Complete Node Implementation
Based on the geometric identity H²+Q²=1.

Features:
- Triangle transactions (each transaction is a quantum triangle)
- Simplex sharding (supports any dimension d; for qutrits, d=3)
- Heat kernel consensus (validator states evolve via e^{-tL})
- Geometric signatures (private Q, public H = sqrt(1-Q²))
- Entropy‑guarded gas metering (gas cost ∝ 1/|α²-β²|)
- P2P networking (simulated with threads)
- JSON‑RPC server
- Command‑line interface

Usage:
    python quantum_simplex_node.py [--port PORT] [--connect HOST:PORT]
"""

import hashlib
import json
import math
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

# ============================================================================
# 1. GEOMETRIC PRIMITIVES
# ============================================================================

class QuantumTriangle:
    """A quantum triangle: A=(0,0), B=(α²,0), C=(β² cos φ, β² sin φ)."""
    def __init__(self, alpha: float, beta: float, phase: float):
        # Normalize so that α + β = 1
        s = alpha + beta
        if s > 0:
            alpha /= s
            beta /= s
        else:
            alpha = beta = 0.5
        self.alpha = alpha
        self.beta = beta
        self.phase = phase % (2 * math.pi)

    @property
    def H(self) -> float:
        """Hypotenuse (classical certainty)."""
        return math.sqrt(1 - 4 * self.alpha * self.beta * math.sin(self.phase/2)**2)

    @property
    def Q(self) -> float:
        """Coherence (phase‑weighted)."""
        return 2 * math.sqrt(self.alpha * self.beta) * abs(math.sin(self.phase/2))

    @property
    def area(self) -> float:
        """Triangle area."""
        return 0.5 * self.alpha * self.beta * abs(math.sin(self.phase))

    @staticmethod
    def from_bytes(data: bytes) -> 'QuantumTriangle':
        """Derive triangle from any data (e.g., transaction ID)."""
        h = hashlib.sha256(data).digest()
        alpha = int.from_bytes(h[:8], 'big') / 2**64
        beta  = int.from_bytes(h[8:16], 'big') / 2**64
        phase = (int.from_bytes(h[16:24], 'big') / 2**64) * 2 * math.pi
        return QuantumTriangle(alpha, beta, phase)

    def to_dict(self) -> dict:
        return {'alpha': self.alpha, 'beta': self.beta, 'phase': self.phase}

    @classmethod
    def from_dict(cls, d: dict) -> 'QuantumTriangle':
        return cls(d['alpha'], d['beta'], d['phase'])


class Simplex:
    """A (d-1)-simplex formed by d triangles (vertices)."""
    def __init__(self, vertices: List[QuantumTriangle]):
        self.vertices = vertices
        self.d = len(vertices)

    @property
    def volume(self) -> float:
        """Simplex volume = 1/(d-1)! * ∏ α_i (simplified)."""
        if self.d < 2:
            return 0.0
        prod = 1.0
        for v in self.vertices:
            prod *= v.alpha
        return prod / math.factorial(self.d - 1)

    @property
    def determinant(self) -> int:
        """Zeta‑regularized determinant = d^{d-1}."""
        return self.d ** (self.d - 1)

    def to_dict(self) -> dict:
        return {'d': self.d, 'vertices': [v.to_dict() for v in self.vertices]}

    @classmethod
    def from_dict(cls, d: dict) -> 'Simplex':
        vertices = [QuantumTriangle.from_dict(v) for v in d['vertices']]
        return cls(vertices)


# ============================================================================
# 2. TRANSACTIONS & SIGNATURES
# ============================================================================

class Transaction:
    def __init__(self, sender: str, receiver: str, amount: float, signature: Optional[int] = None):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = time.time()
        self.signature = signature
        self.id = f"{sender}:{receiver}:{amount}:{self.timestamp}"
        self.triangle = QuantumTriangle.from_bytes(self.id.encode())

    def sign(self, private_Q: float):
        """Sign by XOR‑ing message coherence with private Q."""
        Qm = self.triangle.Q
        self.signature = int(Qm * 2**64) ^ int(private_Q * 2**64)

    def verify(self, public_H: float) -> bool:
        """Verify signature using public H."""
        if self.signature is None:
            return False
        Qm = self.triangle.Q
        recovered_Q = (self.signature ^ int(Qm * 2**64)) / 2**64
        return abs(math.sqrt(1 - recovered_Q**2) - public_H) < 1e-6

    def to_dict(self) -> dict:
        return {
            'sender': self.sender,
            'receiver': self.receiver,
            'amount': self.amount,
            'timestamp': self.timestamp,
            'signature': self.signature,
            'id': self.id,
            'triangle': self.triangle.to_dict()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Transaction':
        tx = cls(d['sender'], d['receiver'], d['amount'], d['signature'])
        tx.timestamp = d['timestamp']
        tx.id = d['id']
        tx.triangle = QuantumTriangle.from_dict(d['triangle'])
        return tx


# ============================================================================
# 3. BLOCK & BLOCKCHAIN
# ============================================================================

class Block:
    def __init__(self, transactions: List[Transaction], prev_hash: str, dimension: int = 3):
        self.transactions = transactions
        self.prev_hash = prev_hash
        self.dimension = dimension
        self.nonce = 0
        self.timestamp = time.time()
        self._hash = None
        self._simplex = None

    @property
    def simplex(self) -> Simplex:
        if self._simplex is None:
            vertices = [tx.triangle for tx in self.transactions[:self.dimension]]
            while len(vertices) < self.dimension:
                vertices.append(QuantumTriangle(0.5, 0.5, 0))
            self._simplex = Simplex(vertices)
        return self._simplex

    @property
    def volume(self) -> float:
        return self.simplex.volume

    @property
    def hash(self) -> str:
        if self._hash is None:
            data = json.dumps({
                'prev_hash': self.prev_hash,
                'timestamp': self.timestamp,
                'nonce': self.nonce,
                'transactions': [tx.to_dict() for tx in self.transactions],
                'dimension': self.dimension
            }, sort_keys=True)
            self._hash = hashlib.sha256(data.encode()).hexdigest()
        return self._hash

    def mine(self, target_volume: float):
        """Proof‑of‑Geometry: increase nonce until simplex volume >= target."""
        while self.volume < target_volume:
            self.nonce += 1
            self._hash = None
            self._simplex = None

    def is_valid(self) -> bool:
        for tx in self.transactions:
            if not tx.triangle.is_valid():
                return False
        if self.volume <= 0:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            'hash': self.hash,
            'prev_hash': self.prev_hash,
            'timestamp': self.timestamp,
            'nonce': self.nonce,
            'dimension': self.dimension,
            'transactions': [tx.to_dict() for tx in self.transactions],
            'volume': self.volume
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Block':
        txs = [Transaction.from_dict(tx) for tx in d['transactions']]
        block = cls(txs, d['prev_hash'], d['dimension'])
        block.nonce = d['nonce']
        block.timestamp = d['timestamp']
        block._hash = d['hash']
        return block


class Blockchain:
    def __init__(self, dimension: int = 3, target_block_time: float = 5.0, adjustment_interval: int = 10):
        self.dimension = dimension
        self.chain = []
        self.pending_transactions = []
        self.difficulty = 1.0
        self.target_block_time = target_block_time
        self.adjustment_interval = adjustment_interval
        self._init_genesis()

    def _init_genesis(self):
        genesis_tx = Transaction("genesis", "network", 0)
        genesis_block = Block([genesis_tx], "0"*64, self.dimension)
        genesis_block.mine(0.1)   # minimal volume
        self.chain.append(genesis_block)

    def add_transaction(self, tx: Transaction):
        self.pending_transactions.append(tx)

    def mine_block(self, miner_address: str) -> Optional[Block]:
        if not self.pending_transactions:
            return None
        prev_hash = self.chain[-1].hash
        target = 1 / self.difficulty
        new_block = Block(self.pending_transactions.copy(), prev_hash, self.dimension)
        new_block.mine(target)
        if new_block.is_valid():
            self.chain.append(new_block)
            self.pending_transactions = []
            self._adjust_difficulty()
            return new_block
        return None

    def _adjust_difficulty(self):
        if len(self.chain) < self.adjustment_interval + 1:
            return
        recent = self.chain[-self.adjustment_interval-1:-1]
        if not recent:
            return
        timestamps = [b.timestamp for b in recent]
        actual_time = timestamps[-1] - timestamps[0]
        expected_time = self.target_block_time * self.adjustment_interval
        ratio = expected_time / actual_time if actual_time > 0 else 1.0
        self.difficulty *= ratio
        self.difficulty = max(0.1, min(1000, self.difficulty))

    def get_balance(self, address: str) -> float:
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.receiver == address:
                    balance += tx.amount
                if tx.sender == address:
                    balance -= tx.amount
        return balance

    def validate_chain(self) -> bool:
        for i in range(1, len(self.chain)):
            if self.chain[i].prev_hash != self.chain[i-1].hash:
                return False
            if not self.chain[i].is_valid():
                return False
        return True

    def get_security_parameter(self) -> int:
        return self.dimension ** (self.dimension - 1)

    def to_dict(self) -> dict:
        return {
            'dimension': self.dimension,
            'chain': [b.to_dict() for b in self.chain],
            'difficulty': self.difficulty
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Blockchain':
        bc = cls(d['dimension'])
        bc.chain = [Block.from_dict(b) for b in d['chain']]
        bc.difficulty = d['difficulty']
        return bc


# ============================================================================
# 4. HEAT KERNEL CONSENSUS (Validator States)
# ============================================================================

class HeatKernelConsensus:
    def __init__(self, n_validators: int):
        self.n = n_validators
        self.states = [1.0 / n_validators] * n_validators   # uniform initial

    def evolve(self, dt: float = 0.1):
        """One step of the heat equation dP/dt = -L P."""
        uniform = 1.0 / self.n
        decay = math.exp(-self.n * dt)
        self.states = [uniform + decay * (p - uniform) for p in self.states]

    def converge(self, epsilon: float = 1e-6) -> int:
        steps = 0
        while max(abs(p - 1/self.n) for p in self.states) > epsilon:
            self.evolve()
            steps += 1
        return steps

    @property
    def spectral_gap(self) -> float:
        return self.n

    def mixing_time(self, epsilon: float = 0.01) -> float:
        return (1 / self.n) * math.log(1 / epsilon)


# ============================================================================
# 5. WALLET (Geometric Keys)
# ============================================================================

class Wallet:
    def __init__(self, private_Q: Optional[float] = None):
        if private_Q is not None:
            self._private_Q = private_Q
            self._public_H = math.sqrt(1 - private_Q**2)
        else:
            self._private_Q = random.random()
            self._public_H = math.sqrt(1 - self._private_Q**2)

    @property
    def address(self) -> str:
        # Simple address from public H
        return hex(int(self._public_H * 2**64))[2:]

    @property
    def public_key(self) -> float:
        return self._public_H

    def sign_transaction(self, tx: Transaction):
        tx.sign(self._private_Q)

    @staticmethod
    def verify_transaction(tx: Transaction, public_H: float) -> bool:
        return tx.verify(public_H)

    def entropy_factor(self) -> float:
        """For a 2‑state account, E = |α²-β²|. Here we simulate with balance."""
        # In a real implementation, this would read from the account's state.
        # We'll use a placeholder: the private Q as a proxy for entropy.
        return abs(self._private_Q**2 - (1 - self._private_Q**2))

    def save(self, filename: str, password: str):
        # Simple encryption for demo (omit for now)
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        f = Fernet(key)
        data = json.dumps({'private_Q': self._private_Q, 'public_H': self._public_H}).encode()
        encrypted = f.encrypt(data)
        with open(filename, 'wb') as fw:
            fw.write(salt + encrypted)

    @classmethod
    def load(cls, filename: str, password: str) -> 'Wallet':
        import base64, os
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        with open(filename, 'rb') as fr:
            data = fr.read()
        salt = data[:16]
        encrypted = data[16:]
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        f = Fernet(key)
        decrypted = f.decrypt(encrypted)
        d = json.loads(decrypted)
        return cls(d['private_Q'])


# ============================================================================
# 6. P2P NETWORK (Simulated)
# ============================================================================

class P2PNode:
    VERSION = 1

    def __init__(self, host='0.0.0.0', port=8333):
        self.host = host
        self.port = port
        self.peers = set()
        self.running = False
        self.handlers = {}
        self.sock = None

    def start(self):
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.sock.accept()
                threading.Thread(target=self._handle_connection, args=(client, addr), daemon=True).start()
            except:
                pass

    def _handle_connection(self, client, addr):
        # Handshake: version exchange
        try:
            msg = self._recv_message(client)
            if msg is None or msg.get('type') != 'version':
                client.close()
                return
            self._send_message(client, {'type': 'version', 'version': self.VERSION, 'port': self.port})
            if msg.get('version') == self.VERSION:
                self.peers.add((addr[0], addr[1]))
                self._handle_client(client)
            else:
                client.close()
        except:
            client.close()

    def _handle_client(self, client):
        while self.running:
            try:
                msg = self._recv_message(client)
                if msg is None:
                    break
                msg_type = msg.get('type')
                if msg_type in self.handlers:
                    self.handlers[msg_type](msg, client)
            except:
                break
        client.close()

    def _send_message(self, sock, msg):
        data = json.dumps(msg).encode()
        sock.sendall(struct.pack('>I', len(data)) + data)

    def _recv_message(self, sock):
        len_data = sock.recv(4)
        if not len_data:
            return None
        msg_len = struct.unpack('>I', len_data)[0]
        data = b''
        while len(data) < msg_len:
            chunk = sock.recv(min(4096, msg_len - len(data)))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode())

    def send_to_peer(self, peer, msg):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(peer)
            self._send_message(s, {'type': 'version', 'version': self.VERSION, 'port': self.port})
            resp = self._recv_message(s)
            if resp and resp.get('version') == self.VERSION:
                self._send_message(s, msg)
            s.close()
        except:
            pass

    def broadcast(self, msg):
        for peer in list(self.peers):
            self.send_to_peer(peer, msg)

    def register_handler(self, msg_type, handler):
        self.handlers[msg_type] = handler

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()


# ============================================================================
# 7. JSON‑RPC SERVER
# ============================================================================

from http.server import HTTPServer, BaseHTTPRequestHandler

class RPCRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
            method = req.get('method')
            params = req.get('params', [])
            result = self.server.node.handle_rpc(method, params)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'result': result, 'error': None}).encode())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({'result': None, 'error': str(e)}).encode())

    def log_message(self, fmt, *args):
        pass


class RPCServer:
    def __init__(self, node, port=8332):
        self.node = node
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self):
        self.httpd = HTTPServer(('0.0.0.0', self.port), RPCRequestHandler)
        self.httpd.node = self.node
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        print(f"RPC server running on port {self.port}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()


# ============================================================================
# 8. MAIN NODE (CLI)
# ============================================================================

class QuantumSimplexNode:
    def __init__(self, port=8333, seed_peer=None, data_file='chain.json', wallet_file='wallet.dat'):
        self.port = port
        self.seed_peer = seed_peer
        self.data_file = data_file
        self.wallet_file = wallet_file
        self.blockchain = None
        self.wallet = None
        self.p2p = P2PNode(port=port)
        self.rpc = RPCServer(self, port=8332)
        self._init_chain()
        self._init_wallet()
        self._register_handlers()

    def _init_chain(self):
        import os
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                self.blockchain = Blockchain.from_dict(data)
        else:
            self.blockchain = Blockchain(dimension=3)

    def _init_wallet(self):
        import os
        if os.path.exists(self.wallet_file):
            pwd = input("Wallet password: ")
            self.wallet = Wallet.load(self.wallet_file, pwd)
        else:
            self.wallet = Wallet()
            pwd = input("New wallet password: ")
            self.wallet.save(self.wallet_file, pwd)

    def _register_handlers(self):
        def on_block(msg, sock):
            block_dict = msg['block']
            block = Block.from_dict(block_dict)
            if block.prev_hash == self.blockchain.chain[-1].hash and block.is_valid():
                self.blockchain.chain.append(block)
                self.p2p.broadcast(msg)
        self.p2p.register_handler('block', on_block)

        def on_tx(msg, sock):
            tx_dict = msg['transaction']
            tx = Transaction.from_dict(tx_dict)
            # Verify signature using sender's public key (we'd need a lookup)
            # For demo, assume valid if signature exists
            if tx.signature is not None:
                self.blockchain.add_transaction(tx)
                self.p2p.broadcast(msg)
        self.p2p.register_handler('transaction', on_tx)

    def start(self):
        self.p2p.start()
        self.rpc.start()
        if self.seed_peer:
            host, port = self.seed_peer.split(':')
            self.p2p.peers.add((host, int(port)))
            print(f"Connected to seed {self.seed_peer}")

        # Start mining loop in background
        def mining_loop():
            while True:
                time.sleep(2)
                if self.blockchain.pending_transactions:
                    block = self.blockchain.mine_block(self.wallet.address)
                    if block:
                        print(f"Mined block {block.hash[:8]}... volume={block.volume:.4f}")
                        self.p2p.broadcast({'type': 'block', 'block': block.to_dict()})
        threading.Thread(target=mining_loop, daemon=True).start()

        # CLI
        print(f"Quantum Simplex Node running on port {self.port}")
        print(f"Your address: {self.wallet.address}")
        print("Commands: send <to> <amount>, balance, mine, peers, info, entropy, exit")
        while True:
            try:
                cmd = input("> ").strip().split()
                if not cmd:
                    continue
                if cmd[0] == 'send':
                    to = cmd[1]
                    amount = float(cmd[2])
                    tx = Transaction(self.wallet.address, to, amount)
                    self.wallet.sign_transaction(tx)
                    self.blockchain.add_transaction(tx)
                    self.p2p.broadcast({'type': 'transaction', 'transaction': tx.to_dict()})
                    print(f"Transaction added: {tx.id[:16]}...")
                elif cmd[0] == 'balance':
                    print(f"Balance: {self.blockchain.get_balance(self.wallet.address):.2f}")
                elif cmd[0] == 'mine':
                    block = self.blockchain.mine_block(self.wallet.address)
                    if block:
                        print(f"Mined block {block.hash[:8]}...")
                    else:
                        print("No transactions to mine")
                elif cmd[0] == 'peers':
                    for p in self.p2p.peers:
                        print(p)
                elif cmd[0] == 'info':
                    print(f"Chain height: {len(self.blockchain.chain)}")
                    print(f"Difficulty: {self.blockchain.difficulty:.4f}")
                    print(f"Security parameter: {self.blockchain.get_security_parameter()}")
                elif cmd[0] == 'entropy':
                    e = self.wallet.entropy_factor()
                    print(f"Your entropy factor E = {e:.4f}")
                    gas = 21000 * (1 + 1/(e+1e-6))
                    print(f"Estimated gas cost: {gas:.0f}")
                elif cmd[0] == 'exit':
                    break
            except Exception as e:
                print(f"Error: {e}")

        # Save on exit
        with open(self.data_file, 'w') as f:
            json.dump(self.blockchain.to_dict(), f)
        self.p2p.stop()
        self.rpc.stop()

    def handle_rpc(self, method, params):
        if method == 'getbalance':
            addr = params[0] if params else self.wallet.address
            return self.blockchain.get_balance(addr)
        elif method == 'sendtransaction':
            to = params[0]
            amount = float(params[1])
            tx = Transaction(self.wallet.address, to, amount)
            self.wallet.sign_transaction(tx)
            self.blockchain.add_transaction(tx)
            self.p2p.broadcast({'type': 'transaction', 'transaction': tx.to_dict()})
            return tx.id
        elif method == 'getblockcount':
            return len(self.blockchain.chain)
        elif method == 'getblock':
            idx = int(params[0])
            if 0 <= idx < len(self.blockchain.chain):
                return self.blockchain.chain[idx].to_dict()
            return None
        elif method == 'getinfo':
            return {
                'version': '1.0',
                'blocks': len(self.blockchain.chain),
                'difficulty': self.blockchain.difficulty,
                'dimension': self.blockchain.dimension,
                'security': self.blockchain.get_security_parameter()
            }
        else:
            raise Exception(f"Unknown method {method}")


# ============================================================================
# 9. ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Quantum Simplex Blockchain Node')
    parser.add_argument('--port', type=int, default=8333, help='Listening port')
    parser.add_argument('--connect', type=str, help='Seed peer to connect to (host:port)')
    args = parser.parse_args()

    node = QuantumSimplexNode(port=args.port, seed_peer=args.connect)
    node.start()
