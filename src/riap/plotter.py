import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def plot_parameter_comparison(res_path, out_path, folder_to_time, parameter_file="totP_prism_cv.xlsx"):

    # Path to your Excel file
    file_path = res_path / parameter_file  # adjust if needed
    df = pd.read_excel(file_path, index_col=0)  # assuming the first column is an index
    df.index = [folder_to_time.get(int(idx), idx) if str(idx).isdigit() else idx for idx in df.index]
    x_values = pd.to_numeric(df.index, errors='coerce')

    if x_values.isna().any():
        x_values = np.arange(len(df.index), dtype=float)
        x_tick_labels = [str(idx) for idx in df.index]
    else:
        x_values = x_values.to_numpy(dtype=float)
        x_tick_labels = [f"{x:g}" for x in x_values]

    # Split columns into two conditions
    num_columns = df.shape[1]
    split_index = num_columns // 2

    condition1 = df.iloc[:, :split_index]
    condition2 = df.iloc[:, split_index:]

    # Number of samples per condition
    n1 = condition1.shape[1]
    n2 = condition2.shape[1]

    # Row-wise statistics
    mean1 = condition1.mean(axis=1) 
    std1 = condition1.std(axis=1)
    sem1 = std1 / np.sqrt(n1)
    ci1 = 1.96 * sem1

    mean2 = condition2.mean(axis=1)
    std2 = condition2.std(axis=1)
    sem2 = std2 / np.sqrt(n2)
    ci2 = 1.96 * sem2

    # Plot
    plt.figure()

    # Condition 1
    line1, = plt.plot(x_values, mean1, linestyle='-', label='GM')
    plt.scatter(x_values, mean1, s=35, color=line1.get_color(), zorder=3)
    plt.fill_between(x_values, mean1 - ci1, mean1 + ci1, alpha=0.3)

    # Condition 2
    line2, = plt.plot(x_values, mean2, linestyle='-', label='WM')
    plt.scatter(x_values, mean2, s=35, color=line2.get_color(), zorder=3)
    plt.fill_between(x_values, mean2 - ci2, mean2 + ci2, alpha=0.3)

    plt.xticks(x_values, x_tick_labels)
    plt.xlabel("Time (mins)")
    plt.ylabel("Value")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path / parameter_file.replace(".xlsx", ".pdf").replace("_prism", ""))
    plt.close()