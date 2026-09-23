"""Run paired 2048-to-2048 episodes concurrently and checkpoint each result."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import textarena as ta
from textarena.decision_bench.runner import PROTOCOL_VERSION, RandomPolicy, run_episode
from textarena.decision_bench.systemone import SystemOnePolicy

VERSIONS = ("v1", "v2", "v3", "v4", "random")
GAME = "2048-v0"


def run_job(
    version: str, seed: int, endpoint: str, model: str, api_key_env: str
) -> tuple[str, dict]:
    if version == "random":
        policy = RandomPolicy(seed)
        prompt_version = "v4"
    else:
        policy = SystemOnePolicy(
            name="jev", endpoint=endpoint, model=model, api_key_env=api_key_env
        )
        prompt_version = version
    result = run_episode(
        GAME, policy, seed=seed, max_decisions=None, prompt_version=prompt_version
    )
    return version, result


def source_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    source = hashlib.sha256()
    files = [root / "scripts/run_full2048.py"]
    files.extend((root / "textarena").rglob("*.py"))
    files.extend((root / "textarena/envs/Game2048/locales").glob("*.json"))
    for path in sorted(files):
        source.update(str(path.relative_to(root)).encode())
        source.update(path.read_bytes())
    return source.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--versions", default=",".join(VERSIONS))
    parser.add_argument("--endpoint", default="https://api.typesafe.ai/v1/systemone")
    parser.add_argument("--model", default="jev-1.13.0")
    parser.add_argument("--api-key-env", default="TYPESAFE_API_KEY")
    args = parser.parse_args()
    if args.episodes < 1 or args.workers < 1:
        parser.error("episodes and workers must be positive")
    versions = tuple(version.strip() for version in args.versions.split(","))
    if (
        not versions
        or len(set(versions)) != len(versions)
        or set(versions) - set(VERSIONS)
    ):
        parser.error(
            "--versions must be a unique comma-separated subset of v1,v2,v3,v4,random"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / "episodes.jsonl"
    manifest_path = args.output_dir / "manifest.json"
    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "textarena_version": ta.__version__,
        "source_digest": source_digest(),
        "game": GAME,
        "first_seed": args.seed,
        "episodes_per_game": args.episodes,
        "versions": list(versions),
        "model": args.model,
        "endpoint_digest": hashlib.sha256(args.endpoint.encode()).hexdigest(),
    }
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            parser.error("output directory has an incompatible run manifest")
    elif checkpoint.exists():
        parser.error("checkpoint has no run manifest")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    results = {}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            entry = json.loads(line)
            results[(entry["version"], entry["result"]["seed"])] = entry["result"]

    pending = [
        (version, seed)
        for seed in range(args.seed, args.seed + args.episodes)
        for version in versions
        if (version, seed) not in results
        or not results[(version, seed)]["completed"]
        or str(results[(version, seed)]["terminal_reason"]).startswith("policy_error:")
    ]
    print(f"Running {len(pending)} episodes with {args.workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_job, version, seed, args.endpoint, args.model, args.api_key_env
            ): (
                version,
                seed,
            )
            for version, seed in pending
        }
        with checkpoint.open("a") as output:
            for future in as_completed(futures):
                version, result = future.result()
                entry = {"version": version, "result": result}
                output.write(json.dumps(entry) + "\n")
                output.flush()
                results[(version, result["seed"])] = result
                print(
                    f"{version} seed={result['seed']} decisions={result['decisions']} "
                    f"max_tile={result['max_tile']} completed={result['completed']}",
                    flush=True,
                )

    metadata = SystemOnePolicy(
        name="jev",
        endpoint=args.endpoint,
        model=args.model,
        api_key_env=args.api_key_env,
    ).metadata()
    for version in versions:
        rows = [
            results[(version, seed)]
            for seed in range(args.seed, args.seed + args.episodes)
        ]
        data = {
            "protocol_version": PROTOCOL_VERSION,
            "prompt_version": "v4" if version == "random" else version,
            "textarena_version": ta.__version__,
            "policy_metadata": {"kind": "random_baseline"}
            if version == "random"
            else metadata,
            "first_seed": args.seed,
            "episodes_per_game": args.episodes,
            "max_decisions": None,
            "results": rows,
        }
        (args.output_dir / f"{version}.json").write_text(
            json.dumps(data, indent=2) + "\n"
        )
    if any(not row["completed"] for row in results.values()):
        parser.exit(1, "incomplete episodes remain; rerun to resume them\n")


if __name__ == "__main__":
    main()
