import argparse
import pprint

from src.pipeline import run_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train and forecast live crypto/stock prices (default: BTC-USD)."
    )
    parser.add_argument(
        "--ticker", default="BTC-USD", help="Ticker or crypto symbol to analyze."
    )
    parser.add_argument(
        "--intraday-days",
        type=int,
        default=7,
        help="How many days of intraday data to pull.",
    )
    parser.add_argument(
        "--invest",
        type=float,
        default=None,
        help="Maximum dollars to deploy per buy signal.",
    )
    parser.add_argument(
        "--force-retrain",
        action="store_true",
        help="Ignore cached models and retrain from scratch.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=50000,
        help="Maximum number of intraday points to fetch (e.g., 50000-100000).",
    )
    parser.add_argument(
        "--train-window",
        type=int,
        default=None,
        help="Limit training to most recent N rows (optional).",
    )
    parser.add_argument(
        "--minute-horizon",
        type=int,
        default=1,
        help="Forecast horizon in 1-minute steps for the short-term model.",
    )
    parser.add_argument(
        "--long-horizon-steps",
        type=int,
        default=9,
        help="Forecast steps for the longer-horizon model (5m bars; 9 ~ 45m).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = run_pipeline(
            ticker=args.ticker,
            intraday_days=args.intraday_days,
            invest_amount=args.invest,
            force_retrain=args.force_retrain,
            max_points=args.max_points,
            train_window=args.train_window,
            minute_horizon=args.minute_horizon,
            long_horizon_steps=args.long_horizon_steps,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        print(
            "Hint: ensure internet access, try --intraday-days 5, or use a different ticker."
        )
        return

    print(f"Ticker: {result['ticker']}")
    print(f"Latest price: ${result['latest_price']:.2f}")
    print(f"Next minute forecast: ${result['next_minute_price']:.2f}")
    print(f"~Next hour (45m) forecast: ${result['next_hour_price']:.2f}")
    print(f"Minute model MAE: {result['minute_mae']}")
    print(f"Hour model MAE: {result['hour_mae']}")
    print("Portfolio simulation:")
    pprint.pprint(result["portfolio"])


if __name__ == "__main__":
    main()
