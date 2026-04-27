#!/usr/bin/env python3
"""
cli.py — 命令行入口
"""
import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from rubric import score_skill
from critique import run_critique, clear_critique, health_check
from optimizer import run_optimization, get_status


def main():
    parser = argparse.ArgumentParser(description="Skill Optimizer CLI")
    sub = parser.add_subparsers(dest="command")

    # score
    score_parser = sub.add_parser("score", help="8-dimension scoring")
    score_parser.add_argument("skill_name", help="Skill name or path")
    score_parser.add_argument("--test-prompts", help="JSON file with test prompts")

    # critique
    critique_parser = sub.add_parser("critique", help="Deep critique + manual generation")
    critique_parser.add_argument("skill_name", help="Skill name")
    critique_parser.add_argument("--no-score", action="store_true", help="Skip scoring")

    # optimize
    opt_parser = sub.add_parser("optimize", help="Optimization loop with ratchet")
    opt_parser.add_argument("skill_name", help="Skill name")
    opt_parser.add_argument("--rounds", type=int, default=3, help="Max rounds")
    opt_parser.add_argument("--auto", action="store_true", help="Auto-confirm")
    opt_parser.add_argument("--no-critique", action="store_true", help="Skip critique")

    # status
    status_parser = sub.add_parser("status", help="Show optimization status")
    status_parser.add_argument("skill_name", nargs="?", help="Skill name (optional)")

    # clear
    clear_parser = sub.add_parser("clear", help="Clear critique reports")
    clear_parser.add_argument("skill_name", help="Skill name")

    # health
    sub.add_parser("health", help="System health check")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "score":
        test_prompts = None
        if args.test_prompts:
            with open(args.test_prompts) as f:
                test_prompts = json.load(f)
        result = score_skill(args.skill_name, test_prompts=test_prompts)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "critique":
        rubric_result = None
        if not args.no_score:
            rubric_result = score_skill(args.skill_name)
        result = run_critique(args.skill_name, rubric_result=rubric_result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "optimize":
        rubric_result = score_skill(args.skill_name)
        critique_result = None
        if not args.no_critique:
            critique_result = run_critique(args.skill_name, rubric_result=rubric_result)
        
        result = run_optimization(
            args.skill_name,
            max_rounds=args.rounds,
            auto_confirm=args.auto,
            rubric_result=rubric_result,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "status":
        result = get_status(args.skill_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "clear":
        result = clear_critique(args.skill_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "health":
        result = health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
