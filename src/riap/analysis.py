"""Statistical helpers for RIAP parameter analysis and export preparation."""

import matplotlib.pyplot as plt
import numpy as np
import re
import pandas as pd
from scipy.stats import circmean, circstd


def load_data_mm(path_MM, angle=0):
    mat = dict(np.load(path_MM))
    azimuth = mat['azimuth']
    if angle != 0:
        azimuth_corrected = np.zeros(azimuth.shape)
        for idx, row in enumerate(azimuth):
            for idy, value in enumerate(row):
                azimuth_corrected[idx, idy] = (value - angle) % 180
        mat['azimuth'] = azimuth_corrected
    return mat


def pad_dataframe_with_nans(df, total_columns):
    n_missing = total_columns - df.shape[1]

    if n_missing > 0:
        for _ in range(n_missing):
            df[f'col_{df.shape[1] + 1}'] = np.nan
    return df


def get_statistics(values, param, parameter):
    listed = values
    listed = listed[listed != 0]
    try:
        assert len(listed) > 0
        if parameter == 'azimuth':
            mean = circmean(listed, high=180)
            stdev = circstd(listed, high=180)
            median = mean
        else:
            mean = np.mean(listed)
            stdev = np.std(listed)
            median = np.median(listed)
    except Exception:
        mean = np.nan
        stdev = np.nan
        median = np.nan
    bins = np.linspace(param['borders'][0], param['borders'][1], num=param['num_bins'])
    data = plt.hist(listed, bins=bins)
    plt.close()
    arr = data[0]
    max_idx = np.where(arr == np.amax(arr))[0][0]
    maximum = data[1][max_idx]
    return mean, stdev, maximum, median


def natural_sort_key(name):
    match = re.search(r'_t(\d+)_', name)
    return int(match.group(1)) if match else float('inf')


def sort_stats_dict(stats_dict):
    return {key: stats_dict[key] for key in sorted(stats_dict, key=natural_sort_key)}


def create_pandas_stats(all_stats):
    all_stats_pandas = {}
    for key_roi, values in all_stats.items():
        dfs = []
        for folder, val in values.items():
            df = pd.DataFrame(val).T
            df.columns = ["mean", "std", "max", "median"]
            df["folder"] = folder
            dfs.append(df)
        dfs = pd.concat(dfs)
        dfs = dfs.reset_index().rename(columns={"index": "parameter"})
        dfs = dfs.sort_values(by=["parameter", "folder"]).reset_index(drop=True)
        all_stats_pandas[key_roi] = dfs
    return all_stats_pandas


def get_angle(fname):
    with open(fname) as file_obj:
        lines = file_obj.readlines()
    for line in lines:
        if 'TransformParameters ' in line:
            angle_data = line
    angle_data = angle_data.split(' ')[1:5]
    angle = np.arctan(float(angle_data[2]) / float(angle_data[0]))
    return angle * 360 / (2 * np.pi)


def subtract_angle(targetA, sourceA):
    a = targetA - sourceA
    return abs((a + 90) % 180 - 90)
