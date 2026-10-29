#!/usr/bin/env python3
"""IND-CPA-style simulation with fresh pads, PRF and fixed-pad encryption.

Install: pip install -r requirements.txt
Run: python ind_cpa_regression.py --n 8 16 32 --queries 32 128 --trials 200

Educational experiment: finite samples cannot establish negligible advantage.
The fixed-pad scheme reuses G(seed) for every encryption, violating IND-CPA.
SHAKE256 is a concrete XOF. Here seed and pad have equal lengths, so this
implementation does not demonstrate the stretch required of a formal PRG.
"""
import argparse
import csv
import hashlib
import hmac
import secrets
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge


def xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def bit_vector(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(np.float64)


class OTP:
    """Fresh, independent one-time pad for every encryption."""

    def __init__(self, nbytes: int):
        self.nbytes = nbytes

    def encrypt(self, message: bytes) -> bytes:
        return xor(message, secrets.token_bytes(self.nbytes))


class PRF:
    """Randomized encryption: nonce || (HMAC_k(nonce) XOR message).

    The nonce length equals the message length; tiny n is deliberately
    used to visualize nonce-collision effects, not claim concrete security.
    """

    def __init__(self, nbytes: int):
        self.nbytes = nbytes
        self.key = secrets.token_bytes(nbytes)

    def encrypt(self, message: bytes) -> bytes:
        nonce = secrets.token_bytes(self.nbytes)
        pad = hmac.new(self.key, nonce, hashlib.sha256).digest()[:self.nbytes]
        return nonce + xor(message, pad)


class PRG:
    """Fixed-pad example inspired by the EAV-secure PRG construction.

    A single seed defines a fixed pad G(seed), reused for EVERY encryption
    in this game. One chosen-plaintext query of all-zero bytes reveals it.
    SHAKE256 is used as an illustrative concrete generator. This version
    does not stretch its seed, so it is not a formal PRG construction.
    """

    def __init__(self, nbytes: int):
        seed = secrets.token_bytes(nbytes)
        self.pad = hashlib.shake_256(seed).digest(nbytes)

    def encrypt(self, message: bytes) -> bytes:
        return xor(message, self.pad)


SCHEMES = {'otp': OTP, 'prf': PRF, 'prg': PRG}


def adversary_game(scheme_name: str, nbits: int, queries: int,
                   alpha: float, rng: np.random.Generator) -> bool:
    if nbits % 8:
        raise ValueError('nbits must be divisible by 8')
    nbytes = nbits // 8
    scheme = SCHEMES[scheme_name](nbytes)
    x_train, y_train = [], []

    # Chosen-plaintext oracle: attacker chooses each message.
    for _ in range(queries):
        message = rng.bytes(nbytes)
        ciphertext = scheme.encrypt(message)
        x_train.append(bit_vector(ciphertext))
        y_train.append(bit_vector(message))

    # Fit a linear approximation of decryption, without secret-key access.
    model = Ridge(alpha=alpha)
    model.fit(np.stack(x_train), np.stack(y_train))

    # Fresh, distinct challenge messages chosen by the adversary.
    m0 = rng.bytes(nbytes)
    m1 = rng.bytes(nbytes)
    while m1 == m0:
        m1 = rng.bytes(nbytes)
    b = secrets.randbelow(2)
    challenge = scheme.encrypt(m0 if b == 0 else m1)

    predicted = model.predict(bit_vector(challenge)[None, :])[0]
    d0 = np.sum((predicted - bit_vector(m0)) ** 2)
    d1 = np.sum((predicted - bit_vector(m1)) ** 2)
    guess = secrets.randbelow(2) if np.isclose(d0, d1) else int(d1 < d0)
    return guess == b


def plot_results(rows: list[dict], schemes: list[str], queries: list[int],
                 image: Path) -> None:
    import matplotlib.pyplot as plt

    for scheme in schemes:
        for q in queries:
            selected = [r for r in rows
                        if r['scheme'] == scheme and r['queries'] == q]
            plt.plot([r['n_bits'] for r in selected],
                     [r['win_rate'] for r in selected], marker='o',
                     label=f'{scheme}, q={q}')
    plt.axhline(0.5, linestyle='--', color='gray', label='random guess')
    plt.xlabel('Message length (bits)')
    plt.ylabel('Observed IND-CPA win rate')
    plt.legend()
    plt.tight_layout()
    plt.savefig(image, dpi=160)
    plt.close()
    print(f'Saved {image}')


def run(args):
    rng = np.random.default_rng(args.seed)
    rows = []
    for scheme in args.schemes:
        for n in args.n:
            for q in args.queries:
                wins = sum(adversary_game(scheme, n, q, args.alpha, rng)
                           for _ in range(args.trials))
                p = wins / args.trials
                se = (p * (1 - p) / args.trials) ** 0.5
                row = {
                    'scheme': scheme, 'n_bits': n, 'queries': q,
                    'trials': args.trials, 'wins': wins,
                    'win_rate': round(p, 6),
                    'signed_advantage': round(p - 0.5, 6),
                    'estimated_advantage': round(abs(p - 0.5), 6),
                    'ci95_low': round(max(0.0, p - 1.96 * se), 6),
                    'ci95_high': round(min(1.0, p + 1.96 * se), 6),
                }
                rows.append(row)
                print(f"{scheme:3s} n={n:3d} q={q:5d} "
                      f"win={p:.3f} adv={abs(p - .5):.3f}", flush=True)
    path = Path(args.output)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'\nSaved {path}')
    if args.plot:
        image = path.with_suffix('.png')
        plot_results(rows, args.schemes, args.queries, image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schemes', nargs='+', choices=SCHEMES, default=list(SCHEMES))
    parser.add_argument('--n', nargs='+', type=int, default=[8, 16, 32])
    parser.add_argument('--queries', nargs='+', type=int, default=[32, 128])
    parser.add_argument('--trials', type=int, default=200)
    parser.add_argument('--alpha', type=float, default=1.0)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--output', default='ind_cpa_results.csv')
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    if any(n <= 0 or n % 8 for n in args.n):
        parser.error('all n values must be positive multiples of 8')
    if any(q < 2 for q in args.queries) or args.trials <= 0 or args.alpha < 0:
        parser.error('queries must be >=2, trials >0, alpha >=0')
    if 'prf' in args.schemes and any(n > 256 for n in args.n):
        parser.error('PRF message lengths must be at most 256 bits')
    run(args)


if __name__ == '__main__':
    main()
