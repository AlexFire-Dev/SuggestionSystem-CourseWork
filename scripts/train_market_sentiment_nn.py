import argparse
import json
import math
import random
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


CLASSES = ["bearish", "neutral", "bullish", "stressed"]
CLASS_TO_ID = {name: idx for idx, name in enumerate(CLASSES)}

FEATURE_NAMES = [
    "spread_bbo",
    "book_vol_imbalance",
    "trade_direction_imbalance",
    "log_trades",
    "state_liquidity_stress",
    "state_active_cancellations",
    "state_buy_pressure",
    "state_sell_pressure",
    "spread_delta",
    "book_imbalance_delta",
    "trade_direction_delta",
    "spread_ma_3",
    "spread_ma_6",
    "book_imbalance_ma_3",
    "trade_direction_ma_3",
    "trades_ma_3",
    "stress_ratio_6",
]


def parse_items(values):
    items = []
    for value in values:
        items.extend(value.replace(",", " ").split())
    return [item.strip().upper() for item in items if item.strip()]


def parse_dates(args):
    result = set()

    for value in args.dates or []:
        result.add(value.strip())

    if args.date_from and args.date_to:
        start = date.fromisoformat(args.date_from)
        end = date.fromisoformat(args.date_to)

        current = start
        while current <= end:
            result.add(current.isoformat())
            current += timedelta(days=1)

    return sorted(result)


def num(row, key, default=0.0):
    value = row.get(key, default)
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def cache_path(cache_dir, secid, trade_date):
    return Path(cache_dir) / f"intraday_{secid}_{trade_date}.json"


def fetch_intraday(base_url, secid, trade_date, limit, cache_dir, refresh_cache=False):
    path = cache_path(cache_dir, secid, trade_date)

    if path.exists() and not refresh_cache:
        return json.loads(path.read_text(encoding="utf-8"))

    query = urllib.parse.urlencode(
        {
            "secid": secid,
            "trade_date": trade_date,
            "limit": limit,
        }
    )
    url = f"{base_url.rstrip('/')}/market/intraday?{query}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SuggestionSystem-ML-Trainer/2.0"},
    )

    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read().decode("utf-8")
        data = json.loads(raw)

    if not isinstance(data, list):
        data = []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    time.sleep(0.15)

    return data


def rolling_mean(rows, index, key, window):
    start = max(0, index - window + 1)
    values = [num(row, key) for row in rows[start : index + 1]]
    values = [value for value in values if math.isfinite(value)]

    if not values:
        return 0.0

    return sum(values) / len(values)


def rolling_stress_ratio(rows, index, window):
    start = max(0, index - window + 1)
    chunk = rows[start : index + 1]

    if not chunk:
        return 0.0

    return sum(1 for row in chunk if str(row.get("market_state") or "") == "liquidity_stress") / len(chunk)


def row_features(rows, index):
    row = rows[index]
    prev_row = rows[max(0, index - 1)]

    state = str(row.get("market_state") or "")

    spread = num(row, "spread_bbo")
    prev_spread = num(prev_row, "spread_bbo")

    book_imbalance = num(row, "book_vol_imbalance")
    prev_book_imbalance = num(prev_row, "book_vol_imbalance")

    trade_direction = num(row, "trade_direction_imbalance")
    prev_trade_direction = num(prev_row, "trade_direction_imbalance")

    trades = max(0.0, num(row, "trades"))

    return [
        spread,
        book_imbalance,
        trade_direction,
        math.log1p(trades),
        1.0 if state == "liquidity_stress" else 0.0,
        1.0 if state == "active_cancellations" else 0.0,
        1.0 if state == "buy_pressure" else 0.0,
        1.0 if state == "sell_pressure" else 0.0,
        spread - prev_spread,
        book_imbalance - prev_book_imbalance,
        trade_direction - prev_trade_direction,
        rolling_mean(rows, index, "spread_bbo", 3),
        rolling_mean(rows, index, "spread_bbo", 6),
        rolling_mean(rows, index, "book_vol_imbalance", 3),
        rolling_mean(rows, index, "trade_direction_imbalance", 3),
        rolling_mean(rows, index, "trades", 3),
        rolling_stress_ratio(rows, index, 6),
    ]


def future_label(rows, index, horizon, global_avg_spread):
    future = rows[index + 1 : index + 1 + horizon]

    if not future:
        return "neutral"

    future_spread = sum(num(row, "spread_bbo") for row in future) / len(future)
    future_book_imbalance = sum(num(row, "book_vol_imbalance") for row in future) / len(future)
    future_trade_direction = sum(num(row, "trade_direction_imbalance") for row in future) / len(future)

    stress_ratio = sum(
        1 for row in future if str(row.get("market_state") or "") == "liquidity_stress"
    ) / len(future)

    if stress_ratio >= 0.34 or future_spread >= global_avg_spread * 1.25:
        return "stressed"

    if future_trade_direction >= 0.25 and future_book_imbalance >= 0.05:
        return "bullish"

    if future_trade_direction <= -0.25 and future_book_imbalance <= -0.05:
        return "bearish"

    return "neutral"


def build_dataset(base_url, tickers, dates, limit, horizon, cache_dir, refresh_cache):
    x_rows = []
    y_rows = []
    meta_rows = []
    loaded = []
    skipped = []

    for ticker in tickers:
        for trade_date in dates:
            print(f"FETCH {ticker} {trade_date}")

            try:
                rows = fetch_intraday(
                    base_url=base_url,
                    secid=ticker,
                    trade_date=trade_date,
                    limit=limit,
                    cache_dir=cache_dir,
                    refresh_cache=refresh_cache,
                )
            except Exception as exc:
                print(f"SKIP {ticker} {trade_date}: {exc}")
                skipped.append({"secid": ticker, "trade_date": trade_date, "reason": str(exc)})
                continue

            rows = sorted(rows, key=lambda row: (str(row.get("trade_date")), str(row.get("trade_time"))))

            if len(rows) <= horizon + 8:
                print(f"SKIP {ticker} {trade_date}: not enough rows ({len(rows)})")
                skipped.append({"secid": ticker, "trade_date": trade_date, "reason": f"not enough rows: {len(rows)}"})
                continue

            spreads = [num(row, "spread_bbo") for row in rows if num(row, "spread_bbo") > 0]
            global_avg_spread = sum(spreads) / len(spreads) if spreads else 1.0

            before_count = len(x_rows)

            for index in range(6, len(rows) - horizon - 1):
                x_rows.append(row_features(rows, index))
                label = future_label(rows, index, horizon, global_avg_spread)
                y_rows.append(CLASS_TO_ID[label])
                meta_rows.append(
                    {
                        "secid": ticker,
                        "trade_date": trade_date,
                        "trade_time": rows[index].get("trade_time"),
                        "label": label,
                    }
                )

            added = len(x_rows) - before_count
            loaded.append({"secid": ticker, "trade_date": trade_date, "rows": len(rows), "samples": added})
            print(f"OK {ticker} {trade_date}: rows={len(rows)} samples={added}")

    return x_rows, y_rows, meta_rows, loaded, skipped


def normalize_fit(x_rows):
    n_features = len(x_rows[0])
    means = []
    stds = []

    for col in range(n_features):
        values = [row[col] for row in x_rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance) or 1.0

        means.append(mean)
        stds.append(std)

    return means, stds


def normalize_transform(x_rows, means, stds):
    return [
        [(value - means[idx]) / stds[idx] for idx, value in enumerate(row)]
        for row in x_rows
    ]


def softmax(values):
    max_value = max(values)
    exp_values = [math.exp(value - max_value) for value in values]
    total = sum(exp_values)
    return [value / total for value in exp_values]


def init_model(n_features, hidden_size, n_classes, seed):
    rnd = random.Random(seed)

    scale1 = math.sqrt(2.0 / max(1, n_features))
    scale2 = math.sqrt(2.0 / max(1, hidden_size))

    w1 = [
        [rnd.uniform(-scale1, scale1) for _ in range(hidden_size)]
        for _ in range(n_features)
    ]
    b1 = [0.0 for _ in range(hidden_size)]

    w2 = [
        [rnd.uniform(-scale2, scale2) for _ in range(n_classes)]
        for _ in range(hidden_size)
    ]
    b2 = [0.0 for _ in range(n_classes)]

    return w1, b1, w2, b2


def forward(row, w1, b1, w2, b2):
    hidden = []

    for hidden_idx in range(len(b1)):
        value = b1[hidden_idx]

        for feature_idx, feature_value in enumerate(row):
            value += feature_value * w1[feature_idx][hidden_idx]

        hidden.append(math.tanh(value))

    logits = []

    for class_idx in range(len(b2)):
        value = b2[class_idx]

        for hidden_idx, hidden_value in enumerate(hidden):
            value += hidden_value * w2[hidden_idx][class_idx]

        logits.append(value)

    probs = softmax(logits)

    return hidden, logits, probs


def predict(row, w1, b1, w2, b2):
    _, _, probs = forward(row, w1, b1, w2, b2)
    return max(range(len(probs)), key=lambda idx: probs[idx])


def accuracy(x_rows, y_rows, w1, b1, w2, b2):
    if not x_rows:
        return 0.0

    correct = 0

    for row, target in zip(x_rows, y_rows):
        if predict(row, w1, b1, w2, b2) == target:
            correct += 1

    return correct / len(x_rows)


def train_mlp(x_rows, y_rows, hidden_size, epochs, lr, seed, class_weights):
    n_features = len(x_rows[0])
    n_classes = len(CLASSES)

    w1, b1, w2, b2 = init_model(n_features, hidden_size, n_classes, seed)

    rnd = random.Random(seed)
    indices = list(range(len(x_rows)))

    best = None
    best_acc = -1.0

    for epoch in range(1, epochs + 1):
        rnd.shuffle(indices)
        epoch_lr = lr * (0.997 ** epoch)
        total_loss = 0.0

        for row_idx in indices:
            x = x_rows[row_idx]
            y = y_rows[row_idx]
            weight = class_weights.get(y, 1.0)

            hidden, _, probs = forward(x, w1, b1, w2, b2)
            total_loss += -math.log(max(probs[y], 1e-12)) * weight

            dz2 = probs[:]
            dz2[y] -= 1.0
            dz2 = [value * weight for value in dz2]

            old_w2 = [row[:] for row in w2]

            for hidden_idx in range(hidden_size):
                for class_idx in range(n_classes):
                    w2[hidden_idx][class_idx] -= epoch_lr * hidden[hidden_idx] * dz2[class_idx]

            for class_idx in range(n_classes):
                b2[class_idx] -= epoch_lr * dz2[class_idx]

            dz1 = []

            for hidden_idx in range(hidden_size):
                grad = 0.0

                for class_idx in range(n_classes):
                    grad += old_w2[hidden_idx][class_idx] * dz2[class_idx]

                grad *= 1.0 - hidden[hidden_idx] ** 2
                dz1.append(grad)

            for feature_idx in range(n_features):
                for hidden_idx in range(hidden_size):
                    w1[feature_idx][hidden_idx] -= epoch_lr * x[feature_idx] * dz1[hidden_idx]

            for hidden_idx in range(hidden_size):
                b1[hidden_idx] -= epoch_lr * dz1[hidden_idx]

        train_acc = accuracy(x_rows, y_rows, w1, b1, w2, b2)

        if train_acc > best_acc:
            best_acc = train_acc
            best = (
                [row[:] for row in w1],
                b1[:],
                [row[:] for row in w2],
                b2[:],
            )

        if epoch == 1 or epoch % 25 == 0 or epoch == epochs:
            avg_loss = total_loss / len(x_rows)
            print(f"EPOCH {epoch:04d} loss={avg_loss:.4f} train_acc={train_acc:.3f}")

    return best


def label_distribution(y_rows):
    result = {name: 0 for name in CLASSES}

    for label_id in y_rows:
        result[CLASSES[label_id]] += 1

    return result


def class_weights_from_labels(y_rows):
    counts = {}
    for label in y_rows:
        counts[label] = counts.get(label, 0) + 1

    total = len(y_rows)
    n_classes = len(CLASSES)

    weights = {}

    for class_id in range(n_classes):
        count = counts.get(class_id, 1)
        weights[class_id] = total / (n_classes * count)

    return weights


def confusion_matrix(x_rows, y_rows, w1, b1, w2, b2):
    matrix = [[0 for _ in CLASSES] for _ in CLASSES]

    for row, actual in zip(x_rows, y_rows):
        predicted = predict(row, w1, b1, w2, b2)
        matrix[actual][predicted] += 1

    return matrix


def main():
    parser = argparse.ArgumentParser(description="Train pure-Python MLP for market sentiment on larger intraday dataset")
    parser.add_argument("--base-url", default="https://okak.af.shvarev.com/api/v1")
    parser.add_argument("--tickers", nargs="+", default=["SBER"])
    parser.add_argument("--dates", nargs="*", default=[])
    parser.add_argument("--date-from", default=None)
    parser.add_argument("--date-to", default=None)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=350)
    parser.add_argument("--lr", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache-dir", default="data/ml_cache")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--output", default="frontend/models/market_sentiment_nn.json")
    parser.add_argument("--min-samples", type=int, default=80)

    args = parser.parse_args()

    tickers = parse_items(args.tickers)
    dates = parse_dates(args)

    if not dates:
        raise RuntimeError("Pass --dates or --date-from/--date-to")

    x_rows, y_rows, meta_rows, loaded, skipped = build_dataset(
        base_url=args.base_url,
        tickers=tickers,
        dates=dates,
        limit=args.limit,
        horizon=args.horizon,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
    )

    if len(x_rows) < args.min_samples:
        raise RuntimeError(
            f"Not enough samples for training: {len(x_rows)}. "
            f"Required minimum: {args.min_samples}."
        )

    means, stds = normalize_fit(x_rows)
    x_norm = normalize_transform(x_rows, means, stds)

    grouped = list(zip(x_norm, y_rows, meta_rows))
    rnd = random.Random(args.seed)
    rnd.shuffle(grouped)

    split_idx = max(1, int(len(grouped) * 0.8))

    train = grouped[:split_idx]
    valid = grouped[split_idx:]

    train_x = [item[0] for item in train]
    train_y = [item[1] for item in train]

    valid_x = [item[0] for item in valid]
    valid_y = [item[1] for item in valid]

    print(f"SAMPLES total={len(x_rows)} train={len(train_x)} valid={len(valid_x)}")
    print(f"LOADED_SERIES {len(loaded)}")
    print(f"SKIPPED_SERIES {len(skipped)}")
    print(f"LABELS_TOTAL {label_distribution(y_rows)}")
    print(f"LABELS_TRAIN {label_distribution(train_y)}")
    print(f"LABELS_VALID {label_distribution(valid_y)}")

    class_weights = class_weights_from_labels(train_y)
    print(f"CLASS_WEIGHTS {class_weights}")

    w1, b1, w2, b2 = train_mlp(
        x_rows=train_x,
        y_rows=train_y,
        hidden_size=args.hidden,
        epochs=args.epochs,
        lr=args.lr,
        seed=args.seed,
        class_weights=class_weights,
    )

    train_acc = accuracy(train_x, train_y, w1, b1, w2, b2)
    valid_acc = accuracy(valid_x, valid_y, w1, b1, w2, b2)
    matrix = confusion_matrix(valid_x, valid_y, w1, b1, w2, b2)

    model = {
        "type": "mlp_market_sentiment",
        "version": "2.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "classes": CLASSES,
        "class_scores": {
            "bearish": -0.65,
            "neutral": 0.0,
            "bullish": 0.65,
            "stressed": -0.90,
        },
        "feature_names": FEATURE_NAMES,
        "normalization": {
            "mean": means,
            "std": stds,
        },
        "architecture": {
            "input_size": len(FEATURE_NAMES),
            "hidden_size": args.hidden,
            "output_size": len(CLASSES),
            "activation": "tanh",
            "output": "softmax",
        },
        "weights": {
            "w1": w1,
            "b1": b1,
            "w2": w2,
            "b2": b2,
        },
        "training": {
            "base_url": args.base_url,
            "tickers": tickers,
            "dates": dates,
            "horizon_intervals": args.horizon,
            "epochs": args.epochs,
            "learning_rate": args.lr,
            "samples_total": len(x_rows),
            "samples_train": len(train_x),
            "samples_valid": len(valid_x),
            "loaded_series": loaded,
            "skipped_series": skipped,
            "label_distribution": label_distribution(y_rows),
            "train_accuracy": train_acc,
            "valid_accuracy": valid_acc,
            "valid_confusion_matrix": matrix,
            "label_rule": "weak labels from future spread, liquidity stress, order-book imbalance and trade direction",
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"TRAIN ACC {train_acc:.3f}")
    print(f"VALID ACC {valid_acc:.3f}")
    print(f"VALID CONFUSION MATRIX rows=actual cols=pred")
    for class_name, row in zip(CLASSES, matrix):
        print(f"{class_name:8s} {row}")
    print(f"SAVED {output_path}")


if __name__ == "__main__":
    main()
