import numpy as np
import pandas as pd
from itertools import product
from sklearn.metrics import cohen_kappa_score, accuracy_score, roc_auc_score, roc_curve
from scipy.stats import ttest_ind

def find_optimal_weights_and_validate():
    # ========================
    # 1. Data loading and cleaning
    # ========================
    try:
        df = pd.read_excel('SI/rider_state.xlsx')
    except FileNotFoundError:
        print("Error: 'rider_state.xlsx' not found.")
        return
    z_cols = ['Attendance Days Z-score', 'Attendance Rate Z-score', 'Average Daily Orders Z-score']
    for col in z_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=z_cols)
    if df.empty:
        print("Error: No valid data after cleaning.")
        return

    # Actual Elite label
    elite_levels = ['Elite']
    df['is_elite_actual'] = df['Rider Level'].isin(elite_levels).astype(int)

    if df['is_elite_actual'].sum() == 0:
        print("Warning: No Elite riders found. Results may be invalid.")

    print(f"Data loaded: {len(df)} riders, "
          f"Elite count = {df['is_elite_actual'].sum()}")

    # ========================
    # 2. Grid search over normalized weights
    # ========================
    search_range = np.arange(0.0, 1.1, 0.1)
    results = []

    print("Running grid search...")
    for w1, w2, w3 in product(search_range, repeat=3):
        if w1 == 0 and w2 == 0 and w3 == 0:
            continue
        total = w1 + w2 + w3
        nw_days, nw_rate, nw_orders = w1/total, w2/total, w3/total

        composite = (df['Attendance Days Z-score'] * nw_days +
                     df['Attendance Rate Z-score'] * nw_rate +
                     df['Average Daily Orders Z-score'] * nw_orders)

        threshold = composite.quantile(0.9)
        pred = (composite >= threshold).astype(int)
        acc = accuracy_score(df['is_elite_actual'], pred)
        try:
            kappa = cohen_kappa_score(df['is_elite_actual'], pred)
        except ValueError:
            kappa = -1.0
        results.append({
            'w_days': round(nw_days, 3),
            'w_rate': round(nw_rate, 3),
            'w_orders': round(nw_orders, 3),
            'accuracy': acc,
            'kappa': kappa
        })

    results_df = pd.DataFrame(results)
    best_idx = results_df['kappa'].idxmax()
    best_row = results_df.loc[best_idx]
    best_kappa = best_row['kappa']
    best_weights = (best_row['w_days'], best_row['w_rate'], best_row['w_orders'])

    print(f"Grid search complete. Best kappa = {best_kappa:.4f}")
    print(f"Best weights: attendance_days = {best_weights[0]:.3f}, "
          f"attendance_rate = {best_weights[1]:.3f}, "
          f"daily_orders = {best_weights[2]:.3f}")

    # ========================
    # 3. High‑agreement region
    # ========================
    # Define region as all weight sets with kappa ≥ 0.95 * max_kappa
    high_agreement = results_df[results_df['kappa'] >= 0.95 * best_kappa]
    min_acc_region = high_agreement['accuracy'].min()
    mean_kappa_region = high_agreement['kappa'].mean()
    print(f"\nHigh‑agreement region (kappa ≥ {0.95*best_kappa:.4f}):")
    print(f"  Number of weight sets: {len(high_agreement)}")
    print(f"  Minimum accuracy in region: {min_acc_region:.4f}")
    print(f"  Mean kappa in region: {mean_kappa_region:.4f}")

    # ========================
    # 4. Weight ratio (2:1:1 for orders:days:rate)
    # ========================
    wo, wad, war = best_weights[2], best_weights[0], best_weights[1]
    print(f"\nRecovered weight ratio (orders : days : rate) = "
          f"{wo:.3f} : {wad:.3f} : {war:.3f}")

    # ========================
    # 5. Sensitivity analysis
    # ========================
    def apply_perturbation_and_compare(base_weights, factors_list):
        """
        Perturb each weight by given factors, re‑normalize, recompute classification,
        and compare with the original (base) classification.
        Returns DataFrame with switches, kappa, agreement accuracy.
        """
        base_composite = (df['Attendance Days Z-score'] * base_weights[0] +
                          df['Attendance Rate Z-score'] * base_weights[1] +
                          df['Average Daily Orders Z-score'] * base_weights[2])
        base_threshold = base_composite.quantile(0.9)
        base_pred = (base_composite >= base_threshold).astype(int)

        records = []
        for f_days, f_rate, f_orders in factors_list:
            w = np.array([base_weights[0]*f_days,
                          base_weights[1]*f_rate,
                          base_weights[2]*f_orders])
            w = w / w.sum()          # re‑normalize
            comp = (df['Attendance Days Z-score'] * w[0] +
                    df['Attendance Rate Z-score'] * w[1] +
                    df['Average Daily Orders Z-score'] * w[2])
            thr = comp.quantile(0.9)
            pred = (comp >= thr).astype(int)

            switches = (pred != base_pred).sum()
            k = cohen_kappa_score(base_pred, pred)
            agr = accuracy_score(base_pred, pred)
            records.append({
                'f_days': f_days, 'f_rate': f_rate, 'f_orders': f_orders,
                'switches': switches, 'kappa': k, 'agreement_accuracy': agr
            })
        return pd.DataFrame(records)

    # Generate perturbation factors: each weight multiplied by [0.8, 0.9, 1.0, 1.1, 1.2]
    # while the other two stay at 1.0 → 15 scenarios total.
    perturb_factors = [0.8, 0.9, 1.1, 1.2]   
    factors_list = []
    for dim in range(3):                      
        for f in perturb_factors:
            f_vec = [1.0, 1.0, 1.0]
            f_vec[dim] = f
            factors_list.append(tuple(f_vec))

    sens_df = apply_perturbation_and_compare(best_weights, factors_list)
    max_switches = sens_df['switches'].max()
    worst_kappa = sens_df['kappa'].min()
    mean_agreement = sens_df['agreement_accuracy'].mean()

    print("\nSensitivity analysis (±10%/±20% perturbations):")
    print(f"  Max riders switched class: {max_switches}")
    print(f"  Worst‑case agreement kappa: {worst_kappa:.4f}")
    print(f"  Mean agreement accuracy: {mean_agreement:.4f}")

    # ========================
    # 6. Hedges’ g and t‑test
    # ========================
    composite_best = (df['Attendance Days Z-score'] * best_weights[0] +
                      df['Attendance Rate Z-score'] * best_weights[1] +
                      df['Average Daily Orders Z-score'] * best_weights[2])

    elite_scores = composite_best[df['is_elite_actual'] == 1]
    regular_scores = composite_best[df['is_elite_actual'] == 0]

    t_stat, p_val = ttest_ind(elite_scores, regular_scores, equal_var=False)
    # Hedges' g (unbiased Cohen's d)
    n1, n2 = len(elite_scores), len(regular_scores)
    s1, s2 = elite_scores.std(ddof=1), regular_scores.std(ddof=1)
    pooled_std = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
    cohens_d = (elite_scores.mean() - regular_scores.mean()) / pooled_std
    # Correction factor
    correction = 1 - 3/(4*(n1+n2) - 9)
    hedges_g = cohens_d * correction

    print(f"\nGroup separation (composite score):")
    print(f"  Elite mean = {elite_scores.mean():.4f}, Regular mean = {regular_scores.mean():.4f}")
    print(f"  Hedges' g = {hedges_g:.4f}, p = {p_val:.4f}")

    # ========================
    # 7. ROC analysis and threshold comparison
    # ========================
    auc = roc_auc_score(df['is_elite_actual'], composite_best)
    fpr, tpr, roc_thresholds = roc_curve(df['is_elite_actual'], composite_best)
    youden = tpr - fpr
    optimal_idx = np.argmax(youden)
    optimal_threshold = roc_thresholds[optimal_idx]
    operational_threshold = composite_best.quantile(0.9)

    print(f"\nROC analysis:")
    print(f"  AUC = {auc:.4f}")
    print(f"  ROC‑optimal threshold (Youden) = {optimal_threshold:.4f}")
    print(f"  Operational threshold (top 10%) = {operational_threshold:.4f}")

if __name__ == "__main__":
    find_optimal_weights_and_validate()