"""
Double pendulum — a nonlinear (chaotic) ODE system.

Pipeline:
  1. SymPy derives the exact equations of motion via the Lagrangian and the
     Euler-Lagrange equations, then solves for the angular accelerations.
  2. SciPy integrates the resulting first-order system numerically.
  3. A Qt window (matplotlib's Qt backend, binding-agnostic) shows, in tabs:
       - the symbolic Lagrangian and the two equations of motion,
       - angles vs. time,
       - the chaotic trajectory of the lower bob,
       - a live animation.

Requires: numpy, scipy, sympy, matplotlib, and a Qt binding
(PyQt6 / PySide6 / PyQt5 — matplotlib picks whichever is installed).
    pip install numpy scipy sympy matplotlib PyQt6
"""

import sys
import numpy as np
import sympy as sp
from scipy.integrate import solve_ivp

from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.qt_compat import QtWidgets


# ----------------------------------------------------------------------------
# 1. Symbolic model: Lagrangian mechanics
# ----------------------------------------------------------------------------
def build_model():
    """Derive the double-pendulum equations of motion symbolically.

    Returns a dict with LaTeX strings for display, SymPy expressions for
    pretty-printing, and fast numeric functions f1, f2 for the accelerations.
    """
    t = sp.symbols("t")
    m1, m2, l1, l2, g = sp.symbols("m1 m2 l1 l2 g", positive=True)

    th1 = sp.Function("theta1")(t)
    th2 = sp.Function("theta2")(t)

    # Cartesian positions of the two bobs (origin at the pivot, y up).
    x1, y1 = l1 * sp.sin(th1), -l1 * sp.cos(th1)
    x2, y2 = x1 + l2 * sp.sin(th2), y1 - l2 * sp.cos(th2)

    # Kinetic and potential energy -> Lagrangian L = T - V.
    v1sq = sp.diff(x1, t) ** 2 + sp.diff(y1, t) ** 2
    v2sq = sp.diff(x2, t) ** 2 + sp.diff(y2, t) ** 2
    T = sp.Rational(1, 2) * m1 * v1sq + sp.Rational(1, 2) * m2 * v2sq
    V = m1 * g * y1 + m2 * g * y2
    L = T - V

    th1d, th2d = sp.diff(th1, t), sp.diff(th2, t)
    th1dd, th2dd = sp.diff(th1, t, 2), sp.diff(th2, t, 2)

    # Euler-Lagrange:  d/dt(dL/dq') - dL/dq = 0  for q = theta1, theta2.
    EL1 = sp.diff(sp.diff(L, th1d), t) - sp.diff(L, th1)
    EL2 = sp.diff(sp.diff(L, th2d), t) - sp.diff(L, th2)

    # Solve the linear-in-accelerations system for theta1'' and theta2''.
    sol = sp.solve([EL1, EL2], [th1dd, th2dd])
    a1 = sp.simplify(sol[th1dd])
    a2 = sp.simplify(sol[th2dd])

    # Replace time-functions/derivatives with plain symbols (derivatives first
    # so they are matched before the functions inside them are rewritten).
    P1, P2 = sp.symbols("theta_1 theta_2", real=True)
    W1, W2 = sp.symbols("omega_1 omega_2", real=True)
    A1, A2 = sp.symbols("alpha_1 alpha_2", real=True)
    repl = [(th1d, W1), (th2d, W2), (th1, P1), (th2, P2)]

    a1s, a2s = a1.subs(repl), a2.subs(repl)
    L_s = L.subs(repl)

    args = (P1, P2, W1, W2, m1, m2, l1, l2, g)
    f1 = sp.lambdify(args, a1s, "numpy")
    f2 = sp.lambdify(args, a2s, "numpy")

    return {
        "L_tex": sp.latex(L_s),
        "a1_tex": sp.latex(sp.Eq(A1, a1s)),
        "a2_tex": sp.latex(sp.Eq(A2, a2s)),
        "a1_expr": sp.Eq(A1, a1s),
        "a2_expr": sp.Eq(A2, a2s),
        "f1": f1,
        "f2": f2,
    }


# ----------------------------------------------------------------------------
# 2. Numerical integration
# ----------------------------------------------------------------------------
def make_rhs(f1, f2, params):
    """Build the first-order RHS for state y = [theta1, omega1, theta2, omega2]."""
    m1, m2, l1, l2, g = params

    def rhs(t, y):
        th1, w1, th2, w2 = y
        a1 = f1(th1, th2, w1, w2, m1, m2, l1, l2, g)
        a2 = f2(th1, th2, w1, w2, m1, m2, l1, l2, g)
        return [w1, a1, w2, a2]

    return rhs


def integrate(model, params, y0, t_end=20.0, n=4000):
    rhs = make_rhs(model["f1"], model["f2"], params)
    t_eval = np.linspace(0.0, t_end, n)
    return solve_ivp(
        rhs, (0.0, t_end), y0, t_eval=t_eval,
        method="DOP853", rtol=1e-9, atol=1e-9,
    )


def bob_positions(sol, params):
    _, _, l1, l2, _ = params
    th1, th2 = sol.y[0], sol.y[2]
    x1, y1 = l1 * np.sin(th1), -l1 * np.cos(th1)
    x2, y2 = x1 + l2 * np.sin(th2), y1 - l2 * np.cos(th2)
    return x1, y1, x2, y2


# ----------------------------------------------------------------------------
# 3. Qt window
# ----------------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, model, sol, params):
        super().__init__()
        self.setWindowTitle("Double Pendulum — Nonlinear ODE")
        self.resize(1100, 760)

        tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._equations_tab(model), "Equations of Motion")
        tabs.addTab(self._angles_tab(sol), "Angles vs Time")
        tabs.addTab(self._trajectory_tab(sol, params), "Trajectory")
        anim_tab, self._anim = self._animation_tab(sol, params)  # keep ref alive
        tabs.addTab(anim_tab, "Animation")

    def _equations_tab(self, model):
        fig = Figure(figsize=(16, 9))
        ax = fig.add_subplot(111)
        ax.axis("off")
        blocks = [
            (0.95, r"Lagrangian  $\mathcal{L}=T-V$:"),
            (0.86, rf"$\mathcal{{L}} = {model['L_tex']}$"),
            (0.62, r"Equations of motion (from the Euler-Lagrange equations):"),
            (0.50, rf"${model['a1_tex']}$"),
            (0.30, rf"${model['a2_tex']}$"),
        ]
        for y, text in blocks:
            ax.text(0.01, y, text, fontsize=10, va="center", ha="left")

        canvas = FigureCanvas(fig)
        canvas.setMinimumSize(1600, 900)  # let long equations scroll
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(False)
        return scroll

    def _angles_tab(self, sol):
        fig = Figure(figsize=(7, 5))
        ax = fig.add_subplot(111)
        ax.plot(sol.t, sol.y[0], label=r"$\theta_1$")
        ax.plot(sol.t, sol.y[2], label=r"$\theta_2$")
        ax.set_xlabel("t  [s]")
        ax.set_ylabel("angle  [rad]")
        ax.set_title("Angular displacement vs. time")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        return FigureCanvas(fig)

    def _trajectory_tab(self, sol, params):
        _, _, x2, y2 = bob_positions(sol, params)
        fig = Figure(figsize=(6, 6))
        ax = fig.add_subplot(111)
        ax.plot(x2, y2, lw=0.5, color="C3")
        ax.set_aspect("equal")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_title("Trajectory of the lower bob (sensitive to initial conditions)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        return FigureCanvas(fig)

    def _animation_tab(self, sol, params):
        _, _, l1, l2, _ = params
        x1, y1, x2, y2 = bob_positions(sol, params)

        fig = Figure(figsize=(6, 6))
        ax = fig.add_subplot(111)
        R = (l1 + l2) * 1.1
        ax.set_xlim(-R, R)
        ax.set_ylim(-R, R)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        ax.set_title("Live animation")

        rods, = ax.plot([], [], "o-", lw=2, color="C0")
        trace, = ax.plot([], [], "-", lw=0.6, alpha=0.5, color="C3")
        canvas = FigureCanvas(fig)

        step = max(1, len(sol.t) // 1000)
        frames = range(0, len(sol.t), step)

        def init():
            rods.set_data([], [])
            trace.set_data([], [])
            return rods, trace

        def update(i):
            rods.set_data([0, x1[i], x2[i]], [0, y1[i], y2[i]])
            j = max(0, i - 250)
            trace.set_data(x2[j:i + 1], y2[j:i + 1])
            return rods, trace

        anim = FuncAnimation(
            fig, update, frames=frames, init_func=init,
            interval=20, blit=True,
        )
        return canvas, anim


# ----------------------------------------------------------------------------
# 4. Entry point
# ----------------------------------------------------------------------------
def main():
    model = build_model()

    # m1, m2 [kg], l1, l2 [m], g [m/s^2]
    params = (1.0, 1.0, 1.0, 1.0, 9.81)
    # Large initial angles -> strongly nonlinear, chaotic motion.
    y0 = [np.radians(120.0), 0.0, np.radians(-10.0), 0.0]
    sol = integrate(model, params, y0, t_end=20.0, n=4000)

    # Console fallback (guaranteed-readable, regardless of mathtext limits).
    print("Equations of motion:")
    sp.pprint(model["a1_expr"])
    print()
    sp.pprint(model["a2_expr"])

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = MainWindow(model, sol, params)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
