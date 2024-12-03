import psutil


def gather_metrics(test_name, start_time, end_time):
    """
    Gather performance metrics for the given test.
    """
    metrics = {
        "test_name": test_name,
        "execution_time": end_time - start_time,
        "memory_usage": psutil.Process().memory_info().rss,  # in bytes
        "memory_usage_mb": (
            psutil.Process().memory_info().rss / (1024 * 1024)
        ),  # Convert to MB
        "cpu_usage_percent": psutil.cpu_percent(),  # CPU usage percentage
    }

    return metrics


def detect_significant_changes(df, threshold=10):
    print("\t\tChecking for significant changes...")  # Debugging

    if len(df) < 2:
        print("\tNot enough data for comparison.")
        return None

    metrics = [
        "execution_time",
        "memory_usage_mb",
        "cpu_usage_percent",
        "disk_usage_percent",
    ]

    for metric in metrics:
        if metric in df.columns:
            last_two_runs = df[metric].dropna().tail(2).values

            if len(last_two_runs) == 2:
                previous_value, current_value = last_two_runs
                print(
                    f"\t\t\tComparing {metric}: previous={previous_value}, current={current_value}"
                )  # Debugging

                percent_change = 100 * (current_value - previous_value) / previous_value
                # print(f"percent change: {percent_change}")

                if percent_change > threshold:
                    print(
                        f"\t\t\t\tSignificant change detected for {metric}: {percent_change}% change"
                    )
                    return {
                        "Performance_stable": False,
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "percent_change": percent_change,
                    }

    print("\t\tNo significant changes found.")
    return None
