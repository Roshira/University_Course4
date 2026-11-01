import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp

N = 3
r = 2 * N
q = 200 * N
a = 15


def f(x, p):
    return r * x * (1 - x / q) - p


def stationary_points(p):
    d = q ** 2 / 4 - p * q / r
    if d < 0:
        return []
    if d == 0:
        return [q / 2]
    return [q / 2 - np.sqrt(d), q / 2 + np.sqrt(d)]


def stability(x):
    df = r - 2 * r * x / q
    if df < 0:
        return "stable"
    if df > 0:
        return "unstable"
    return "semi"


def sol_case1(x0):
    return lambda t: 300 + (x0 - 300) / (1 + 0.01 * (x0 - 300) * t)


def sol_case2(x0):
    c = (x0 - 450) / (x0 - 150)
    return lambda t: (450 - 150 * c * np.exp(-3 * t)) / (1 - c * np.exp(-3 * t))


def sol_case3(x0):
    return lambda t: 300 + 150 * np.tan(np.arctan((x0 - 300) / 150) - 1.5 * t)


def extinction_time(p, x0, t_max=10):
    def hit_zero(t, x):
        return x[0]

    hit_zero.terminal = True
    hit_zero.direction = -1
    sol = solve_ivp(lambda t, x: f(x, p), (0, t_max), [x0], events=hit_zero, rtol=1e-10, atol=1e-10)
    return sol.t_events[0][0] if len(sol.t_events[0]) else None


def check(p, x0, analytic, t_end):
    ts = np.linspace(0, t_end if t_end else 2, 50)[:-1]
    sol = solve_ivp(lambda t, x: f(x, p), (0, ts[-1]), [x0], t_eval=ts, rtol=1e-10, atol=1e-10)
    return np.max(np.abs(sol.y[0] - analytic(ts)))


def plot_case(filename, p, title, curves, t_max, legend="center right"):
    points = [(x, stability(x)) for x in stationary_points(p)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))

    xs = np.linspace(0, q, 600)
    fv = f(xs, p)
    ax1.plot(xs, fv, color="#1f77b4", lw=2)
    ax1.axhline(0, color="black", lw=0.8)
    for x, kind in points:
        if kind == "stable":
            ax1.plot(x, 0, "o", ms=9, color="#2ca02c", zorder=5)
        elif kind == "unstable":
            ax1.plot(x, 0, "o", ms=9, mfc="white", mec="#d62728", mew=2, zorder=5)
        else:
            ax1.plot(x, 0, "o", ms=9, mfc="white", mec="#ff7f0e", mew=2, zorder=5)
            ax1.plot(x, 0, "o", ms=9, fillstyle="right", color="#ff7f0e", zorder=6)
        ax1.annotate(f"x = {x:g}", (x, 0), textcoords="offset points", xytext=(0, 10), ha="center")
    span = max(fv.max(), 0) - fv.min()
    ax1.set_ylim(fv.min() - 0.05 * span, max(fv.max(), 0) + 0.15 * span)
    ax1.set_xlabel("x")
    ax1.set_ylabel("dx/dt")
    ax1.set_title("Фазова пряма: dx/dt = f(x)")
    ax1.grid(alpha=0.3)

    colors = ["#d62728", "#1f77b4", "#2ca02c"]
    for (x0, solution), color in zip(curves, colors):
        t_end = extinction_time(p, x0)
        ts = np.linspace(0, t_end if t_end else t_max, 800)
        ax2.plot(ts, solution(ts), lw=2, color=color, label=f"x₀ = {x0:g}")
        if t_end:
            ax2.plot(t_end, 0, "x", ms=9, mew=2, color=color)
            ax2.annotate(f"t* ≈ {t_end:.3f}", (t_end, 0), textcoords="offset points", xytext=(6, 8), color=color)
        err = check(p, x0, solution, t_end)
        status = f"зникає при t* = {t_end:.4f}" if t_end else f"x({t_max:g}) = {solution(t_max):.2f}"
        print(f"  x0 = {x0:>4g}: {status}, похибка аналітичного розв'язку {err:.1e}")
    for x, _ in points:
        ax2.axhline(x, ls="--", lw=1, color="gray")
    ax2.axhline(q, ls=":", lw=1, color="gray")
    ax2.set_xlim(0, t_max)
    ax2.set_ylim(-10, q + 20)
    ax2.set_xlabel("t")
    ax2.set_ylabel("x(t)")
    ax2.set_title("Розв'язки x(t)")
    ax2.grid(alpha=0.3)
    ax2.legend(loc=legend)

    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(filename, dpi=160)
    plt.close(fig)


KIND = {"stable": "стійка", "unstable": "нестійка", "semi": "напівстійка"}


def describe(p):
    points = stationary_points(p)
    if not points:
        return "немає стаціонарних точок"
    return ", ".join(f"x = {x:g} ({KIND[stability(x)]})" for x in points)


if __name__ == "__main__":
    p1 = r * q / 4
    p2 = r * q / 4 - a ** 2
    p3 = r * q / 4 + a ** 2
    print(f"N = {N}: r = {r}, q = {q}, a = {a}")

    print(f"Випадок 1: p = {p1:g}, {describe(p1)}")
    plot_case("fish_case1.png", p1, f"Випадок 1: p = rq/4 = {p1:g}",
              [(200, sol_case1(200)), (450, sol_case1(450))], 3, legend="lower right")

    print(f"Випадок 2: p = {p2:g}, {describe(p2)}")
    plot_case("fish_case2.png", p2, f"Випадок 2: p = rq/4 − a² = {p2:g}",
              [(100, sol_case2(100)), (300, sol_case2(300)), (550, sol_case2(550))], 2)

    print(f"Випадок 3: p = {p3:g}, {describe(p3)}")
    plot_case("fish_case3.png", p3, f"Випадок 3: p = rq/4 + a² = {p3:g}",
              [(q / 3, sol_case3(q / 3)), (3 * q / 4, sol_case3(3 * q / 4))], 1.7)

    print("Графіки збережено: fish_case1.png, fish_case2.png, fish_case3.png")
