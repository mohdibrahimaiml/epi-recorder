def calculate_moving_average(data, window_size):
    """Calculate moving average for time series data."""
    if len(data) < window_size:
        return []
    
    moving_avg = []
    for i in range(len(data) - window_size + 1):
        window = data[i:i + window_size]
        moving_avg.append(sum(window) / window_size)
    
    return moving_avg