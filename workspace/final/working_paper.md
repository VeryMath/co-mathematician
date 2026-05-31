# PDHG 还是 Douglas-Rachford？连续优化中算法选择的决策框架

## 摘要

Primal-Dual Hybrid Gradient (PDHG) 和 Douglas-Rachford Splitting (DRS)
是连续优化中两类核心的一阶算子分裂算法。O'Connor & Vandenberghe (2020)
证明了两者的数学等价性——PDHG 可视为 DRS 的特例，反之亦然。
然而，这种等价性并不意味着实际效率相同。本文综合文献调研、理论分析和
数值实验，提出系统性的算法选择决策框架，帮助实践者在给定优化问题时
做出最优选择。

**核心发现**: 选择的主导因素是 Fenchel 共轭函数的邻近算子计算代价
和线性算子的范数。在大多数实际场景中，PDHG 因其对 $\text{prox}_{f^*}$
的有效利用而具有优势（本文实验中达到 11-24× 加速），但 DRS 在特定
条件下（算子范数极大且列满秩、简单复合问题）仍是最优选择。

---

## 1. 引言

### 1.1 问题设定

考虑复合凸优化问题：

$$\min_x \; f(Ax) + g(x)$$

其中 $A: \mathbb{R}^n \to \mathbb{R}^m$ 是线性算子，$f, g$ 是 proper
convex lower-semicontinuous 函数。

### 1.2 两种算法

**Douglas-Rachford Splitting** (Lions & Mercier 1979) 求解 $\min f(x) + g(x)$:

$$x^{k+1} = \text{prox}_{\gamma f}(z^k), \quad y^{k+1} = \text{prox}_{\gamma g}(2x^{k+1} - z^k), \quad z^{k+1} = z^k + \lambda(y^{k+1} - x^{k+1})$$

**PDHG** (Chambolle & Pock 2011) 求解 $\min f(Ax) + g(x)$:

$$y^{k+1} = \text{prox}_{\sigma f^*}(y^k + \sigma A\bar{x}^k), \quad x^{k+1} = \text{prox}_{\tau g}(x^k - \tau A^* y^{k+1}), \quad \bar{x}^{k+1} = 2x^{k+1} - x^k$$

### 1.3 等价性

O'Connor & Vandenberghe (2020) 证明：PDHG 等价于 DRS 应用于 primal-dual
最优性条件 $0 \in [0\; A^\top; -A\; 0][x; y] + [\partial g(x); \partial f^*(y)]$。
这一等价性通过 preconditioned proximal point 视角建立，对应的 metric 矩阵为
$M = \text{blkdiag}(\tau^{-1}I, \sigma^{-1}I - \sigma AA^\top)$。

**推论**: 理论收敛速率相同（一般凸 $O(1/k)$，强凸线性收敛），但常数因子和
每步代价因问题结构而差异巨大。

---

## 2. 理论分析：何时选择哪种算法

### 2.1 Prox 代价比

定义核心指标：

$$R = \frac{\text{cost}(\text{prox}_{f^*})}{\text{cost}(\text{prox}_f)}$$

这是决定性因素：

- **$R < 0.5$**: PDHG 明显更优。$\text{prox}_{f^*}$ 有闭式解而 $\text{prox}_f$
  需迭代求解。典型案例: $f(x) = \frac{1}{2}\|Ax-b\|^2$, $f(x) = \|Dx\|_1$ (TV)。
- **$R > 2$**: DRS 更优。$\text{prox}_f$ 有闭式而 Fenchel 共轭复杂。
- **$R \approx 1$**: 两者相当，继续考察其他指标。

### 2.2 算子范数条件数

$$\kappa = \frac{\|A\|}{\max(1, \sqrt{\mu_g \mu_{f^*}})}$$

PDHG 收敛需满足 $\tau\sigma\|A\|^2 < 1$，大 $\|A\|$ 限制步长。DRS 无此约束。

- $\kappa > 10$ **且** $A$ 列满秩 → DRS 更优
- $\kappa > 10$ **但** $A$ 非列满秩 → DRS 中 $f \circ A$ 失去强凸性 → PDHG + 预条件

### 2.3 预条件

PDHG 天然支持对角线预条件 (Pock & Chambolle 2011):
$\tau_j = 1/\sum_i |A_{ij}|, \sigma_i = 1/\sum_j |A_{ij}|$。
异构尺度问题中显著加速，无需计算全局 $\|A\|$。DRS 预条件需手动设计。

### 2.4 参数敏感性

| 方面 | PDHG | DRS |
|------|------|-----|
| 参数数量 | 3 ($\tau, \sigma, \theta$) | 2 ($\gamma, \lambda$) |
| 耦合约束 | $\tau\sigma\|A\|^2 < 1$ | 无 |
| 对 $\|A\|$ 估计误差的敏感度 | 高（低估→发散） | 低 |
| 现代免调参方案 | 免调参 PDHG (2024), 线搜索 PDHG (2025) | 相对成熟 |

---

## 3. 数值实验验证

在三个经典问题上对比 PDHG 和 DRS：

| 问题 | 规模 | $R$ | PDHG | DRS | 加速比 |
|------|------|-----|------|-----|--------|
| LASSO | 500×200 | $\ll 0.1$ | 0.114s | 1.317s | **11×** |
| TV 去噪 | 128 | $\ll 0.05$ | 0.039s | 0.955s | **24×** |
| 矩阵补全 | 50×50 | $\approx 1$ | 0.287s | 0.329s | 1.1× |

实验结果与理论预测高度一致：当 $\text{prox}_{f^*}$ 有闭式时 PDHG 显著领先；
当两种 prox 代价相当时性能接近。

DRS 在 TV 问题中的劣势尤为突出——每步需要内层 50 步 PDHG 求解的
子问题，使得总时间膨胀 25 倍。

---

## 4. 决策框架

### 4.1 快速决策树

```
问题: min f(Ax) + g(x)
├─ A = I? → 用 R 判断: R<0.5→PDHG, 否则→DRS
├─ f* 的 prox 有闭式? → PDHG ✓
├─ ||A|| 极大 (κ>10)?
│   ├─ A 列满秩 → DRS
│   └─ A 非满秩 → PDHG + 预条件
├─ 需要预条件? → PDHG + 对角预条件
└─ 调参资源有限? → 免调参 PDHG (2024+)
```

### 4.2 推荐评价指标

1. **Prox 代价比** ($R$): 预测性能差异的单一最重要指标
2. **算子范数条件数** ($\kappa$): 影响 PDHG 步长约束和 DRS 强凸性保持
3. **固定点残差**: 衡量迭代稳定性
4. **Wall-clock 时间到目标精度**: 综合收敛速度与每步代价
5. **参数敏感性**: 衡量实际部署的鲁棒性

### 4.3 通用建议

1. **从 PDHG 开始** — 大多数实际问题中 $R < 0.5$，PDHG 是更好的默认选择
2. **不要仅看迭代次数** — TV 实验中 DRS 单步需 50 次内层迭代，wall-clock
   时间才是真正的性能度量
3. **注意 $A$ 的秩** — DRS 应用到 $f \circ A$ 时，非满秩 $A$ 导致收敛率降级
4. **利用等价性** — 一个算法的参数可转换为另一算法的参数，方便交叉验证

---

## 5. 局限性

- 数值实验仅覆盖 $n \leq 500$ 的中等规模问题，大规模场景结论需进一步验证
- 未充分测试 $\kappa \gg 1$ 场景下 DRS 的理论优势
- 非凸问题中的等价性未讨论
- 免调参方法 (2024-2025) 未纳入实验对比

---

## 参考文献

1. Chambolle, A., & Pock, T. (2011). A first-order primal-dual algorithm for convex
   problems with applications to imaging. *JMIV*, 40, 120-145.
2. Chambolle, A., & Pock, T. (2016). An introduction to continuous optimization for
   imaging. *Acta Numerica*, 25, 161-319.
3. Condat, L. (2013). A primal-dual splitting method for convex optimization. *JOTA*,
   158(2), 460-479.
4. Dong, Y., Bredies, K., & Sun, H. (2024). A stochastic preconditioned
   Douglas-Rachford splitting method for saddle-point problems. arXiv:2212.13001.
5. Eckstein, J., & Bertsekas, D. P. (1992). On the Douglas-Rachford splitting method
   and the proximal point algorithm. *Math. Prog.*, 55, 293-318.
6. Fercoq, O. (2024). Monitoring the convergence speed of PDHG to find better primal
   and dual step sizes. arXiv:2403.19202.
7. Giselsson, P., & Boyd, S. (2017). Linear convergence and metric selection for
   Douglas-Rachford splitting and ADMM. *IEEE TAC*, 62(2), 532-544.
8. Goldstein, T., et al. (2015). Adaptive primal-dual hybrid gradient methods for
   saddle-point problems. arXiv:1305.0546.
9. Lions, P. L., & Mercier, B. (1979). Splitting algorithms for the sum of two
   nonlinear operators. *SIAM J. Numer. Anal.*, 16(6), 964-979.
10. McManus, A., Becker, S., & Dwork, N. (2025). A relaxed primal-dual hybrid
    gradient method with line search. arXiv:2503.17575.
11. O'Connor, D., & Vandenberghe, L. (2020). On the equivalence of the primal-dual
    hybrid gradient method and Douglas-Rachford splitting. *Math. Prog.*, 179, 85-108.
12. Ozaslan, I. K., & Jovanović, M. R. (2024). Accelerated forward-backward and
    Douglas-Rachford splitting dynamics. arXiv:2407.20620.
13. Pock, T., & Chambolle, A. (2011). Diagonal preconditioning for first-order
    primal-dual algorithms in convex optimization. *ICCV*, 1762-1769.
14. Wang, H., Lan, G., & Ye, Y. (2024). A tuning-free primal-dual splitting algorithm
    for large-scale semidefinite programming. arXiv:2402.00311.
