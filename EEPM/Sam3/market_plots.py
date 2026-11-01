# Самостійна робота 3, Варіант 3 — попит і пропозиція, субсидія для виробника sub = 0.6
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brentq

P = np.array([1.1, 1.4, 1.75, 2.2, 2.8, 3.25, 4.05, 5.25])
Qd = np.array([120, 95, 73, 55, 42, 36, 28, 20.])
Qs = np.array([20, 33, 50, 62, 75, 84, 98, 125.])
sub = 0.6

# МНК: попит Qd = a/P + b (заміна z = 1/P), пропозиція Qs = c·lnP + d (заміна u = lnP)
a, b = np.polyfit(1 / P, Qd, 1)
c, d = np.polyfit(np.log(P), Qs, 1)
a, b, c, d = round(a, 2), round(b, 2), round(c, 2), round(d, 2)
D = lambda p: a / p + b
S = lambda p: c * np.log(p) + d
S_sub = lambda p: c * np.log(p + sub) + d

def r2(y, yh):
    return 1 - np.sum((y - yh) ** 2) / np.sum((y - y.mean()) ** 2)

p0 = brentq(lambda p: D(p) - S(p), 0.9, 10); q0 = D(p0)
p1 = brentq(lambda p: D(p) - S_sub(p), 0.5, 10); q1 = D(p1)
print(f"D(P) = {a}/P {b:+}   R² = {r2(Qd, D(P)):.4f}")
print(f"S(P) = {c}·lnP {d:+}   R² = {r2(Qs, S(P)):.4f}")
print(f"E0: P* = {p0:.3f}, Q* = {q0:.2f}")
print(f"E1: Pспож = {p1:.3f}, Pвир = {p1 + sub:.3f}, Q = {q1:.2f}, витрати держави = {sub * q1:.2f}")

pp = np.linspace(1.0, 5.6, 300)

# 1. Апроксимація даних
fig, ax = plt.subplots(1, 2, figsize=(8.8, 3.44), dpi=200)
fig.suptitle("Апроксимація функцій попиту та пропозиції (МНК)", fontweight="bold")
ax[0].plot(D(pp), pp, color="tab:blue", lw=2, label=f"Qd = {a}/P − {abs(b)}")
ax[0].plot(Qd, P, "o", color="tab:blue", mfc="white", mew=1.8, ms=7, label="дані")
ax[0].set_title(f"Попит, R² = {r2(Qd, D(P)):.4f}")
ax[1].plot(S(pp), pp, color="tab:orange", lw=2, label=f"Qs = {c}·lnP + {d}")
ax[1].plot(Qs, P, "s", color="tab:orange", mfc="white", mew=1.8, ms=7, label="дані")
ax[1].set_title(f"Пропозиція, R² = {r2(Qs, S(P)):.4f}")
for x in ax:
    x.set_xlabel("Q"); x.set_ylabel("P"); x.grid(alpha=0.3); x.legend()
fig.tight_layout(); fig.savefig("market_fit.png"); plt.close(fig)

# 2. Рівновага до та після субсидії (осі Q, P)
fig, ax = plt.subplots(figsize=(8.8, 5.6), dpi=200)
pp2 = np.linspace(0.85, 6.6, 400)
ax.plot(D(pp2), pp2, color="tab:blue", lw=2, label=f"D: Q = {a}/P − {abs(b)}")
ax.plot(S(pp2), pp2, color="tab:orange", lw=2, label=f"S: Q = {c}·lnP + {d}")
ax.plot(S_sub(pp2), pp2, color="tab:green", lw=2, ls="--", label=f"S₁: Q = {c}·ln(P + {sub}) + {d}")
ax.plot(Qd, P, "o", color="tab:blue", mfc="white", ms=6, alpha=0.7)
ax.plot(Qs, P, "s", color="tab:orange", mfc="white", ms=6, alpha=0.7)
ax.plot(q0, p0, "o", color="black", ms=9, zorder=5)
ax.annotate(f"E₀ ({q0:.2f}; {p0:.2f})", (q0, p0), xytext=(q0 - 30, p0 - 0.45), fontsize=10)
ax.plot(q1, p1, "o", color="tab:red", ms=9, zorder=5)
ax.annotate(f"E₁ ({q1:.2f}; {p1:.2f})", (q1, p1), xytext=(q1 + 3, p1 - 0.45), fontsize=10, color="tab:red")
ax.plot(q1, p1 + sub, "o", color="tab:green", ms=7, zorder=5)
for y, txt, col in [(p0, f"P* = {p0:.2f}", "gray"), (p1, f"Pспож = {p1:.2f}", "tab:red"),
                    (p1 + sub, f"Pвир = {p1 + sub:.2f}", "tab:green")]:
    ax.axhline(y, xmin=0, xmax=(max(q0, q1) - 0) / 140, color=col, ls=":", lw=1)
    ax.text(1, y + 0.05, txt, color=col, fontsize=9)
ax.vlines([q0, q1], 0, [p0, p1 + sub], colors=["gray", "tab:red"], ls=":", lw=1)
ax.annotate("", xy=(q1, p1), xytext=(q1, p1 + sub), arrowprops=dict(arrowstyle="<->", color="tab:green"))
ax.text(q1 + 1, p1 + sub / 2, f"sub = {sub}", color="tab:green", fontsize=9, va="center")
ax.fill_between([0, q1], p1, p1 + sub, color="tab:green", alpha=0.12, label=f"витрати держави = {sub * q1:.2f}")
ax.set_xlim(0, 140); ax.set_ylim(0, 6.6)
ax.set_xlabel("Q"); ax.set_ylabel("P"); ax.grid(alpha=0.3); ax.legend(loc="upper center")
ax.set_title("Ринкова рівновага та вплив субсидії для виробника (sub = 0.6)", fontweight="bold")
fig.tight_layout(); fig.savefig("market_equilibrium.png"); plt.close(fig)

# 3. Павутиноподібна модель — перевірка стійкості
pt = [2.6]; qt = []
for _ in range(14):
    q = S(pt[-1]); qt.append(q); pt.append(a / (q - b))
fig, ax = plt.subplots(1, 2, figsize=(8.8, 3.44), dpi=200)
fig.suptitle("Стійкість рівноваги: павутиноподібна модель", fontweight="bold")
pp3 = np.linspace(1.4, 3.2, 200)
ax[0].plot(D(pp3), pp3, color="tab:blue", lw=2, label="D")
ax[0].plot(S(pp3), pp3, color="tab:orange", lw=2, label="S")
xs, ys = [], []
for i, q in enumerate(qt):
    xs += [q, q]; ys += [pt[i], pt[i + 1]]
ax[0].plot(xs, ys, color="tab:red", lw=1.2, label="траєкторія")
ax[0].plot(q0, p0, "o", color="black", ms=7)
ax[0].set_xlabel("Q"); ax[0].set_ylabel("P"); ax[0].set_title("Фазова діаграма (Q, P)")
ax[0].set_ylim(1.35, 3.7); ax[0].legend(loc="upper center", ncol=3, fontsize=8); ax[0].grid(alpha=0.3)
ax[1].plot(range(len(pt)), pt, "o-", color="tab:red", lw=1.5, ms=5)
ax[1].axhline(p0, color="gray", ls="--", lw=1, label=f"P* = {p0:.2f}")
ax[1].set_ylim(1.65, 2.85); ax[1].legend(loc="upper right", fontsize=8)
ax[1].set_xlabel("t"); ax[1].set_ylabel("Pₜ"); ax[1].set_title("Динаміка ціни Pₜ, P₀ = 2.6")
ax[1].grid(alpha=0.3)
fig.tight_layout(); fig.savefig("market_cobweb.png"); plt.close(fig)
