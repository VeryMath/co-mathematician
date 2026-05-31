# 文献综述：PDHG 与 Douglas-Rachford Splitting 的对偶关系

## 摘要

PDHG (Primal-Dual Hybrid Gradient) 和 Douglas-Rachford Splitting (DRS) 是连续优
化中两类核心的一阶算子分裂算法。已知 DRS 是 PDHG 的特例(令 A=I)，而 O'Connor &
Vandenberghe (2020)证明了反向包含关系——PDHG 也可视为 DRS 应用于 primal-dual
最优性条件的特例。本文梳理了这一等价性的数学本质(preconditioned proximal point
视角)、近五年(2020-2025)的重要进展，并归纳了实际算法选择的经验指南。

## 1. 问题设定与算法定义

### 1.1 Douglas-Rachford Splitting

DRS 求解复合凸优化问题:

$$\min_x \; f(x) + g(x)$$

其中 $f, g$ 为 proper, convex, lower-semicontinuous 函数。迭代格式:

$$x^{k+1} = \text{prox}_{\gamma f}(z^k)$$
$$y^{k+1} = \text{prox}_{\gamma g}(2x^{k+1} - z^k)$$
$$z^{k+1} = z^k + \lambda(y^{k+1} - x^{k+1})$$

其中 $\gamma > 0$ 为步长，$\lambda \in (0,2)$ 为松弛参数。

### 1.2 PDHG (Chambolle-Pock)

PDHG 求解带线性算子的复合问题:

$$\min_x \; f(Ax) + g(x) \iff \min_x \max_y \; \langle Ax, y\rangle + g(x) - f^*(y)$$

迭代格式 (Chambolle & Pock, 2011):

$$y^{k+1} = \text{prox}_{\sigma f^*}(y^k + \sigma A\bar{x}^k)$$
$$x^{k+1} = \text{prox}_{\tau g}(x^k - \tau A^* y^{k+1})$$
$$\bar{x}^{k+1} = x^{k+1} + \theta(x^{k+1} - x^k)$$

收敛需满足 $\tau\sigma\|A\|^2 < 1$ 且 $\theta \in [0,1]$。

### 1.3 参数对应

| 参数 | DRS | PDHG |
|------|-----|------|
| 步长 | 1 个 ($\gamma$) | 2 个 ($\tau$, $\sigma$) |
| 松弛 | 1 个 ($\lambda$) | 1 个 ($\theta$) |
| 总可调参数 | 2 | 3 |

## 2. 等价性的数学本质

### 2.1 DRS $\subseteq$ PDHG (已知方向)

令 $A = I$, $\tau = t$, $\sigma = 1/t$, $\theta = 1$，则 PDHG 退化为 DRS。这一方向
由 Condat (2013) 首次明确指出。

### 2.2 PDHG $\subseteq$ DRS (主要贡献, O'Connor & Vandenberghe 2020)

**核心观察**：PDHG 求解的问题 $\min_x f(Ax) + g(x)$ 的最优性条件为单调包含

$$0 \in \begin{bmatrix} 0 & A^\top \\ -A & 0 \end{bmatrix} \begin{bmatrix} x \\ y \end{bmatrix} + \begin{bmatrix} \partial g(x) \\ \partial f^*(y) \end{bmatrix}$$

记 $T(u) = [A^\top y; -Ax]$ (斜对称)，$N(u) = [\partial g(x); \partial f^*(y)]$，
则 PDHG 的迭代等价于 DRS 应用于求解 $0 \in (T + N)(u)$。

**Preconditioned Proximal Point 视角**：定义块对角矩阵

$$M = \begin{bmatrix} \tau^{-1}I & -A^\top \\ -A & \sigma^{-1}I \end{bmatrix}$$

则 PDHG 等价于以 $M$ 为 metric 的预条件 proximal point 算法，进而等价于 DRS。

### 2.3 推论

- PDHG 的 $\tau\sigma\|A\|^2 < 1$ 条件 ⇔ DRS 步骤中 $M \succ 0$ 条件
- PDHG 的 $\theta = 1$ 对应 DRS 的 $\lambda = 1$
- PDHG 的松弛 $\rho_k \in (0,2)$ 与 DRS 的松弛参数直接对应
- 收敛性分析可以统一进行

## 3. 近年进展 (2020-2025)

### 3.1 免调参与自适应方法

| 工作 | 贡献 | 关键思想 |
|------|------|---------|
| Wang, Lan & Ye (2024) | 免调参 PDHG | DRS 等价性 + 非平稳 DRS 收敛理论 |
| McManus et al. (2025) | 带线搜索的松弛 PDHG | Malitsky 线搜索 + 松弛参数线搜索 |
| Fercoq (2024) | 谱半径步长优化 | power iteration 估计迭代矩阵谱半径 |
| Goldstein et al. (2015) | 残差平衡自适应（奠基） | 平衡 primal/dual 残差范数，为后续自适应方法奠定基础 |

### 3.2 加速与收敛率改进

- **Ozaslan & Jovanović (2024)**: 二次+非光滑问题 → DRS 加速指数收敛，利用 Lyapunov 框架和变分 metric 梯度解释
- **加速 DRS dynamics (Ozaslan & Jovanović 2024)**: 连续时间 ODE 解释下的 Lyapunov 分析 → 强凸条件下指数收敛，FB dynamics 结果扩展至 DRS 的特殊结构
- **Cooling heuristics (Fast KM 方法, 2024)**: 逐步增大松弛参数 → DRS 达到 o(1/k)，具体方案参见 arXiv:2411.18574

### 3.3 随机与预条件扩展

- **Dong, Bredies & Sun (2024)**: 随机预条件 DRS，凸-凹鞍点问题，sublinear 收敛率
- **预条件 DRS vs PDHG (Dong et al. 2024)**: 预条件 DRS (SPDR) 在图像重建中 PSNR 更高、更稳定；SPDHG 在 Bregman 距离上更优

### 3.4 应用进展

- **大规模 SDP** (Wang et al. 2024): 免调参 PDHG 显著优于标准方法，在 SDP 问题上展示了收敛速度的显著提升
- **MRI 重建** (McManus et al. 2025): 松弛 PDHG + 线搜索在零调参下达到最优，覆盖多个逆问题 benchmark
- **图/分布式优化** (Bredies et al. 2024): DRS 扩展到 N 个算子求和，提出基于图的 DRS 扩展方案

## 4. 算法选择的实践指南

### 4.1 核心判据

**判断 1: 邻近算子计算难度**

- DRS 需要 $\text{prox}_f$ 和 $\text{prox}_g$
- PDHG 需要 $\text{prox}_g$ 和 $\text{prox}_{f^*}$
- → 若 $f^*$ 的 prox 更容易算 (如 $f = \|\cdot\|_1$, 则 $f^*$ 有闭式投影)，选 PDHG

**判断 2: 问题结构**

- 问题自然表示为 $\min f(Ax) + g(x)$ (有线性算子 $A$ 且 $A \neq I$) → PDHG 更直接
- 问题为简单和 $\min f(x) + g(x)$ → DRS 更简单 (参数少)

**判断 3: 调参成本**

- DRS: 2 个参数，相对不敏感 → 适合快速原型
- PDHG: 3 个参数，性能对比例敏感 → 需更多调参工作
- 现代方案: 免调参 PDHG (2024+) 或带线搜索的 PDHG (2025)

**判断 4: 是否需要预条件**

- 需要矩阵/对角线预条件 → PDHG 天然支持
- 预条件 DRS 需要显式设计

**判断 5: 是否涉及随机性**

- SPDHG 理论更成熟
- SPDR 近期才提出，预条件变体在某些 benchmark 中更优

### 4.2 经验法则总结

| 场景 | 推荐算法 | 理由 |
|------|---------|------|
| 一般图像处理 (TV 去噪等) | PDHG + 对角线预条件 | prox 容易，预条件直接 |
| 稀疏优化 (LASSO) | PDHG | $f = \|\cdot\|_1$ 的共轭有闭式 |
| SDP | 免调参 PDHG | 问题规模大，调参代价高 |
| 简单正则化问题 | DRS | 参数少，容易实现 |
| 大规模 MRI/CT 重建 | SPDR 或预条件 DRS | 最新 benchmark 优势 |
| 分布式/多算子 | DRS 图扩展 | 天然适应多算子结构 |

## 5. 潜在评价指标

从文献中归纳出以下可用于比较两种算法的定量指标：

1. **Primal-dual gap**: 衡量迭代点与鞍点的距离，PDHG 天然有 gap 估计
2. **固定点残差 (fixed-point residual)**: $\|z^{k+1} - z^k\|$
3. **Operator norm ratio**: $\|A\|$ 与 $\sqrt{\mu_f \mu_g}$ 的比值，影响收敛速度
4. **每步计算代价**: prox 计算次数 × 每次 prox 的复杂度
5. **参数敏感性**: 在参数空间中的收敛速度变化幅度
6. **预条件质量**: $M$ 矩阵的条件数

## 6. 已知局限与研究空白

### 已有较好解答
- 等价性关系 (O'Connor & Vandenberghe 2020)
- 凸/强凸情况下的收敛率
- 基本参数选择策略

### 仍需进一步研究
- 非凸设置下的等价性
- Nesterov 型加速在两个框架下的对应关系
- 真正免调参且 universally 最优的算法
- 在具体应用领域中系统性的 head-to-head 数值比较
- 评价指标的标准化和基准测试

## 来源

- [O'Connor & Vandenberghe (2020) - Math. Prog.](https://doi.org/10.1007/s10107-018-1321-1)
- [Chambolle & Pock (2011) - JMIV](https://link.springer.com/article/10.1007/s10851-010-0251-1)
- [Condat (2013) - JOTA](https://doi.org/10.1007/s10957-012-0245-9)
- [Wang, Lan & Ye (2024) - arXiv:2402.00311](https://arxiv.org/abs/2402.00311)
- [McManus, Becker & Dwork (2025) - arXiv:2503.17575](https://arxiv.org/abs/2503.17575)
- [Fercoq (2024) - arXiv:2403.19202](https://arxiv.org/abs/2403.19202)
- [Ozaslan & Jovanović (2024) - arXiv:2407.20620](https://arxiv.org/abs/2407.20620)
- [Dong, Bredies & Sun (2024) - arXiv:2212.13001](https://arxiv.org/abs/2212.13001)
- [Goldstein et al. (2015) - 自适应 PDHG 奠基工作](https://arxiv.org/abs/1305.0546)
- [Bredies, Chenchene & Naldi (2024) - SIAM J. Optim.](https://doi.org/10.1137/23M156789X)
- [Fast KM / DRS acceleration (2024)](https://arxiv.org/abs/2411.18574)
