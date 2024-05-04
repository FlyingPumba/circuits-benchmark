from typing import Dict, List

import seaborn as sns
import matplotlib.pyplot as plt
import wandb
from sklearn import metrics

if __name__ == "__main__":
  """Calculates the plots for comparing linear vs non-linear compression."""
  api = wandb.Api()
  runs = api.runs("linear-vs-non-linear")

  metrics = ["accuracy", "cp_loss", "var_exp"]
  metrics_data = {}
  for metric in metrics:
    metrics_data[metric] = {
      "linear": [],
      "non-linear": []
    }

  finished_linear_cases = set()
  finished_non_linear_cases = set()

  running_linear_cases = set()
  running_non_linear_cases = set()

  max_cp_loss = 0
  max_cp_case = None

  min_var_exp = 1
  min_var_exp_case = None

  cases_with_var_exp_below_0 = []

  for run in runs:
    run_name = run.name
    case = run_name.split("case-")[1].split("-")[0]

    method = None
    if "non-linear-compression" in run_name:
      method = "non-linear"
    elif "linear-compression" in run_name:
      method = "linear"
    else:
      continue

    if run.state != "finished":
      print(f"Skipping run {run.name} (Method: {method}, case: {case}) because it is not finished.")

      if run.state == "running":
        if method == "linear":
          running_linear_cases.add(case)
        else:
          running_non_linear_cases.add(case)

    if method == "linear":
      finished_linear_cases.add(case)
    else:
      finished_non_linear_cases.add(case)

    accuracy = run.summary["test_accuracy"]["max"]
    cp_loss = run.summary["test_resample_ablation_loss"]["min"]
    var_exp = run.summary["test_resample_ablation_var_exp"]["max"]

    print(f"Case {case} - Method {method} - Accuracy: {accuracy} - CP Loss: {cp_loss}")

    metrics_data["accuracy"][method].append(accuracy)
    metrics_data["cp_loss"][method].append(cp_loss)
    metrics_data["var_exp"][method].append(var_exp)

    if method == "non-linear":
      if cp_loss > max_cp_loss:
        max_cp_loss = cp_loss
        max_cp_case = case

      if var_exp < min_var_exp:
        min_var_exp = var_exp
        min_var_exp_case = case

      if var_exp < 0:
        cases_with_var_exp_below_0.append(case)

  print(f"Case with max CP loss: {max_cp_case} - CP Loss: {max_cp_loss}")
  print(f"Case with min var exp: {min_var_exp_case} - Var Exp: {min_var_exp}")
  print(f"{len(cases_with_var_exp_below_0)} cases with var exp below 0: {sorted([int(case) for case in cases_with_var_exp_below_0])}")

  # List all the cases that are missing for linear and non-linear.
  # We should have strings for 1 to 39.
  missing_linear_cases = set([str(i) for i in range(1, 40)]) - finished_linear_cases
  missing_non_linear_cases = set([str(i) for i in range(1, 40)]) - finished_non_linear_cases
  print(f"Missing linear cases: {sorted([int(case) for case in missing_linear_cases])}")
  print(f"Missing non-linear cases: {sorted([int(case) for case in missing_non_linear_cases])}")

  print(f"Running linear cases: {sorted([int(case) for case in running_linear_cases])}")
  print(f"Running non-linear cases: {sorted([int(case) for case in running_non_linear_cases])}")

  # Now we have the data, we can calculate the plots
  for metric in metrics:
    data_by_method = metrics_data[metric]
    plt.clf()
    fig, ax = plt.subplots(figsize=(8, 6))  # Increase the figure size

    plt.title(f"{metric} (test data)", fontsize=16)  # Increase the title font size
    plt.xlabel("Method", fontsize=14)
    plt.ylabel(metric, fontsize=14)

    # The order of boxplots should be "linear", "non-linear"
    data = [data_by_method["linear"], data_by_method["non-linear"]]
    labels = ["Linear", "Non-Linear"]

    # Set color palette
    sns.set(style="darkgrid")

    # plot boxplot using pastel colors, without fliers
    ax = sns.boxplot(data, showfliers=False, palette="pastel")
    ax.set_xticklabels(labels)

    # Adjust spacing between subplots
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)

    plt.savefig(f"{metric}-linear-vs-non-linear-compression.png", dpi=300, bbox_inches='tight')
    plt.close(fig)