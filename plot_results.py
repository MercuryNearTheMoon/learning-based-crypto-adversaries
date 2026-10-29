#!/usr/bin/env python3
"""Create IND-CPA result figures from an existing experiment CSV."""

import argparse
import csv
from math import sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


SCHEMES = ('otp', 'prf', 'prg')
COLORS = {'otp': '#377eb8', 'prf': '#4daf4a', 'prg': '#e41a1c'}


def wilson_interval(wins: int, trials: int) -> tuple[float, float]:
    """95% Wilson score interval for the observed win rate."""
    z = 1.96
    p = wins / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    radius = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials**2)) / denominator
    return center - radius, center + radius


def read_results(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f'No result rows in {path}')
    for row in rows:
        row['n_bits'] = int(row['n_bits'])
        row['queries'] = int(row['queries'])
        row['trials'] = int(row['trials'])
        row['wins'] = int(row['wins'])
        row['win_rate'] = row['wins'] / row['trials']
    return rows


def plot_trends(rows: list[dict], output: Path) -> None:
    budgets = sorted({row['queries'] for row in rows})
    fig, axes = plt.subplots(1, len(budgets), figsize=(6 * len(budgets), 4.5),
                             sharey=True, squeeze=False)
    for ax, budget in zip(axes[0], budgets):
        for scheme in SCHEMES:
            selected = sorted((row for row in rows if row['scheme'] == scheme
                               and row['queries'] == budget),
                              key=lambda row: row['n_bits'])
            if not selected:
                continue
            x = [row['n_bits'] for row in selected]
            y = [row['win_rate'] for row in selected]
            intervals = [wilson_interval(row['wins'], row['trials'])
                         for row in selected]
            errors = [[rate - low for rate, (low, _) in zip(y, intervals)],
                      [high - rate for rate, (_, high) in zip(y, intervals)]]
            ax.errorbar(x, y, yerr=errors, marker='o', capsize=3,
                        linewidth=1.8, color=COLORS[scheme], label=scheme.upper())
        ax.axhline(0.5, color='#666666', linestyle='--', linewidth=1,
                   label='Random guess')
        ax.set_title(f'{budget} oracle queries')
        ax.set_xlabel('Message length (bits)')
        ax.set_xticks(sorted({row['n_bits'] for row in rows}))
        ax.set_ylim(0.25, 1.05)
        ax.grid(axis='y', alpha=0.25)
    axes[0][0].set_ylabel('Observed IND-CPA win rate')
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=4,
               bbox_to_anchor=(0.5, 0.91))
    fig.suptitle('Ridge adversary: win rate by message length', y=0.98)
    trial_counts = sorted({row['trials'] for row in rows})
    trial_note = (f'{trial_counts[0]} games per point' if len(trial_counts) == 1
                  else 'game counts vary by point')
    fig.text(0.5, 0.01, f'Error bars: 95% Wilson intervals; {trial_note}',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.84))
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_overview(rows: list[dict], output: Path) -> None:
    settings = sorted({(row['n_bits'], row['queries']) for row in rows})
    lookup = {(row['scheme'], row['n_bits'], row['queries']): row['win_rate']
              for row in rows}
    values = np.array([[lookup.get((scheme, n, q), np.nan) for n, q in settings]
                       for scheme in SCHEMES])
    fig, ax = plt.subplots(figsize=(9, 3.6))
    heatmap = ax.imshow(values, cmap='YlOrRd', vmin=0, vmax=1, aspect='auto')
    ax.set_xticks(range(len(settings)), [f'{n} bits\n{q} queries' for n, q in settings])
    ax.set_yticks(range(len(SCHEMES)), [name.upper() for name in SCHEMES])
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            if np.isfinite(values[i, j]):
                color = 'white' if values[i, j] > 0.75 else 'black'
                ax.text(j, i, f'{values[i, j]:.3f}', ha='center', va='center',
                        color=color, fontsize=10)
    ax.set_title('Observed IND-CPA win rate from CSV (Ridge adversary)')
    fig.colorbar(heatmap, ax=ax, label='Win rate', shrink=0.85)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('plots'))
    args = parser.parse_args()
    rows = read_results(args.csv_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trend = args.output_dir / 'win_rate_by_message_length.png'
    overview = args.output_dir / 'win_rate_overview.png'
    plot_trends(rows, trend)
    plot_overview(rows, overview)
    print(f'Saved {trend}')
    print(f'Saved {overview}')


if __name__ == '__main__':
    main()
