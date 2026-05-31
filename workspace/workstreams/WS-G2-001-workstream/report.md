# 理论分析：PDHG vs Douglas-Rachford 算法选择条件与判据

## 1. 问题形式化的统一视角

### 1.1 一般问题

考虑复合凸优化问题:

$$\min_x \; f(Ax) + g(x)$$

其中 $A: \mathbb{R}^n \to \mathbb{R}^m$ 是线性算子，$f, g$ 是 proper convex l.s.c. 函数。

### 1.2 两种算法的适用范围

| | PDHG | DRS |
|---|---|---|
| 问题形式 | $\min f(Ax) + g(x)$ | $\min f(x) + g(x)$ |
| $A$ | 任意线性算子 | $A = I$ |
| 直接适用 | ✓ | ✓ (令 $\tilde{f} = f \circ A$) |
| 等价性 | 可化为 DRS | 可化为 PDHG |

**关键insight**: 尽管数学上等价，实际问题中 $A$ 的结构决定了哪种形式更自然。

## 2. 收敛率对比分析

### 2.1 一般凸情况

设步长参数满足收敛条件（PDHG: $\tau\sigma\|A\|^2 < 1$, DRS: $\gamma > 0$）。

**PDHG** (Chambolle & Pock 2011, Thm. 1): 遍历序列 $(x^{(k)}, y^{(k)})$ 满足

$$G_B(x^{(k)}, y^{(k)}) \leq \frac{C}{2k}$$

其中 $C = \sup_{(x,y)\in B} \|x-x^0\|^2_{\tau^{-1}} + \|y-y^0\|^2_{\sigma^{-1}}$。

**DRS** (He & Yuan 2012, Thm. 2.1): 同样 $O(1/k)$ 遍历速率。

→ 在一般凸情况下，**理论速率相同**。

### 2.2 强凸情况

情况 A: **仅 $g$ 为 $\mu_g$-强凸**

| 算法 | 速率 |
|------|------|
| PDHG (原始步长) | $O(1/k^2)$ 若选 $\tau_k = 1/(\mu_g k)$ |
| DRS | $O(1/k^2)$ 类似条件 |

情况 B: **$f^*$ 和 $g$ 均为强凸**

| 算法 | 速率 | 条件 |
|------|------|------|
| PDHG | 线性 $O(\omega^k)$ | $\tau, \sigma$ 适当选择 |
| DRS | 线性 $O(\omega^k)$ | $\gamma$ 适当选择 |

**关键差异**: 线性收敛速率常数不同。根据 Chambolle & Pock (2016, Thm. 5) 以及 Giselsson & Boyd (2017, Sec. 4)，最优参数选择下的收缩因子:

$$\omega_{\text{PDHG}} \approx 1 - \frac{2\sqrt{\mu_g \mu_{f^*}}}{2\sqrt{\mu_g \mu_{f^*}} + \|A\|}$$

DRS (Eckstein & Bertsekas 1992, Thm. 5) 的收缩因子为

$$\omega_{\text{DRS}} \approx 1 - \frac{2\sqrt{\mu_f \mu_g}}{\sqrt{\mu_f \mu_g} + 1/\gamma}$$

**重要限制**: DRS 公式中的 $\mu_f$ 是 $f$ 本身的强凸性常数。当 $A \neq I$ 且将 $\tilde{f}=f \circ A$ 代入 DRS 框架时，若 $A$ 非列满秩，则 $\tilde{f}$ 不再强凸（即使 $f$ 强凸），此时公式不适用。这一限制是 DRS 在带线性算子问题上的根本劣势。PDHG 通过 fenchel 共轭 $f^*$ 的强凸性避免了此问题。

→ 当 $\|A\|$ 较大时，PDHG 的线性速率显著慢于 DRS (operator norm 出现在分母)；但当 $A$ 非满秩时 DRS 可能完全失去线性收敛。

### 2.3 算子范数的影响

定义 $\kappa = \frac{\|A\|}{\sqrt{\mu_g \mu_{f^*}}}$ 为条件数指标。

| $\kappa$ 范围 | 含义 | 推荐算法 |
|---|---|---|
| $\kappa \ll 1$ | 算子范数小，primal-dual 耦合弱 | PDHG 或 DRS 均可 |
| $\kappa \approx 1$ | 适度耦合 | 取决于 prox 计算便利性 |
| $\kappa \gg 1$ | 强耦合 | DRS (或在 PDHG 中引入强预条件) |

**理论依据**: 大 $\|A\|$ 使 PDHG 的步长需满足 $\tau\sigma < 1/\|A\|^2$，严重限制步长。

## 3. 每步计算代价分析

### 3.1 基础运算

| 运算 | PDHG | DRS |
|------|------|-----|
| 矩阵-向量乘法 | $Ax$, $A^\top y$ (2 次) | 无需 |
| Prox 计算 | $\text{prox}_{\tau g}$, $\text{prox}_{\sigma f^*}$ | $\text{prox}_{\gamma f}$, $\text{prox}_{\gamma g}$ |
| 向量运算 | 加减、标量乘 | 加减、标量乘 |

### 3.2 Prox 计算代价

**PDHG 需要 $\text{prox}_{f^*}$**: 这可能是优势也可能是劣势
- 优势: 若 $f$ 的 prox 需要迭代求解而 $f^*$ 有闭式 → PDHG 更优
- 劣势: 若 $f$ 的 prox 有闭式而 $f^*$ 需数值计算 → DRS 更优

**具体例子**:
- $f(x) = \|x\|_1$ → $f^*(y) = \iota_{\|\cdot\|_\infty \leq 1}(y)$ → $\text{prox}_{f^*}$ 投影到 $\ell_\infty$ 球 (闭式, $O(n)$) → PDHG 优势明显
- $f(x) = \|Ax - b\|^2$ → $f^*$ 解为 $f^*(y) = \frac{1}{2}\|A(A^\top A)^{-1}y + b\|^2$，复杂 → DRS 更优
- $f(x) = \|x\|_{\text{nuc}}$ (核范数) → $f^*$ 是指示函数 $\iota_{\|\cdot\|_2 \leq 1}$ (谱范数球)，$\text{prox}_{f^*}$ 需投影到谱范数球（同样需要 SVD 对奇异值做投影）。注意：此时 PDHG 和 DRS 都需要每次迭代做 SVD，两者代价相当

### 3.3 矩阵-向量乘积累计代价

对于大 $n$, 每步 PDHG 额外需要 2 次 matrix-vector product:
- $Ax$: $O(mn)$ 若 $A$ 稠密
- 总迭代次数 × matrix-vector cost 可能主导总时间

**DRS 没有这个开销** (因为 $A = I$)。

## 4. 预条件理论

### 4.1 PDHG 的对角线预条件 (Pock & Chambolle 2011)

将步长 $\tau, \sigma$ 推广为对角矩阵:

$$\tau_j = \frac{1}{\sum_i |A_{ij}|}, \quad \sigma_i = \frac{1}{\sum_j |A_{ij}|}$$

**优势**:
- 无需计算全局 $\|A\|$
- 每个坐标独立调整步长
- 对异构问题 (不同坐标尺度差异大) 显著加速

### 4.2 DRS 的预条件

DRS 的预条件等价于以另一内积下的 proximal point 算法。构造更复杂，但可以做到同样效果。

**对比**:
- PDHG: 预条件步长选择有闭式公式
- DRS: 预条件需要手动设计，缺乏通用方法

→ 需要预条件时，PDHG 有更系统的优势。

## 5. 参数敏感性与鲁棒性

### 5.1 Lipschitz 常数估计误差的影响

设 $\|A\|$ 的估计值为 $\hat{L}$，相对误差 $\delta = |\hat{L} - \|A\||/\|A\|$。

**PDHG**: 需满足 $\tau\sigma < 1/\hat{L}^2$
- 若 $\delta > 0$ (高估), 算法仍收敛但步长偏小 → 慢
- 若 $\delta < 0$ (低估), 可能发散 → **敏感**

**DRS**: $\gamma > 0$ 总可收敛
- 性能对 $\gamma$ 的选择相对不敏感
- 没有"步长乘积"约束 → **更鲁棒**

### 5.2 参数搜索空间

- DRS: 搜索空间 2 维 ($\gamma$, $\lambda$)，且 $\lambda \in (0,2)$ 通常取 1 即可
- PDHG: 搜索空间 3 维 ($\tau$, $\sigma$, $\theta$)，且有耦合约束 $\tau\sigma\|A\|^2 < 1$

→ DRS 调参负担显著更低。

### 5.3 免调参进展

近年工作显著降低了 PDHG 的调参难度:
- Wang, Lan & Ye (2024): 利用 DRS 等价性实现免调参
- McManus et al. (2025): 带线搜索的松弛 PDHG，零参数输入

## 6. 松弛参数的作用

### 6.1 理论

PDHG 和 DRS 均有松弛参数 (PDHG: $\rho_k$, DRS: $\lambda$)，在等价性框架下直接对应。

**欠松弛** ($\lambda \to 0$): 稳定但慢
**标准** ($\lambda = 1$): 基准收敛
**过松弛** ($\lambda \in (1, 2)$): 可能加速，但接近 2 时不稳定

### 6.2 Cooling Heuristic

从 $\lambda_0 = 0.5$ 开始，逐步增加到 $\lambda_k \to 2$:
- 初始: 稳定，保证收敛
- 后期: 加速，达到 $o(1/k)$ 实际收敛率

这一策略在 DRS 框架下更容易实现 (单一参数)，但在 PDHG 框架下需要额外考虑与 $\tau,\sigma$ 的相互作用。

## 7. 综合选择判据

### 7.1 理论选择树

```
问题: min f(Ax) + g(x)
├── A = I (无线性算子)?
│   ├── 是 → prox_f 和 prox_g 都好算? → DRS (简单)
│   └── 否 ↓
├── ‖A‖ 很大 (>> 1)?
│   ├── 是 → DRS 更鲁棒 (不受 ‖A‖ 约束)
│   └── 否 ↓
├── prox_{f*} 有闭式?
│   ├── 是 → PDHG (规避了 f 的复杂 prox)
│   └── 否 ↓
├── 需要预条件?
│   ├── 是 → PDHG (对角线预条件天然支持)
│   └── 否 ↓
├── 调参资源有限?
│   ├── 是 → DRS (参数少、不敏感)
│   └── 否 → 均可, 推荐免调参 PDHG (2024+)
```

### 7.2 量化判据

定义以下指标帮助选择:

1. **算子范数比**: $\rho_A = \frac{\|A\|}{\max(1, \sqrt{\mu_g\mu_{f^*}})}$
   - $\rho_A < 1$: PDHG 更优
   - $\rho_A > 10$: DRS 更优

2. **Prox 代价比**: $R = \frac{\text{cost}(\text{prox}_{f^*})}{\text{cost}(\text{prox}_f)}$
   - $R < 0.5$: PDHG 有利
   - $R > 2$: DRS 有利

3. **问题规模指标**: $S = \frac{\text{cost}(Ax)}{\text{cost}(\text{prox}_f)}$
   - $S \ll 1$: PDHG 的额外开销可忽略
   - $S \gg 1$: DRS 更经济

4. **参数敏感性**: 若无法准确估计 $\|A\|$ → DRS 更安全

## 8. 结论

**理论上两者等价，实践中选择取决于**:
1. $A$ 的结构和范数 (越大越倾向 DRS)
2. Fenchel 共轭的 prox 是否容易计算 (越容易越倾向 PDHG)
3. 是否需要预条件 (需要 → PDHG)
4. 调参资源 (有限 → DRS)
5. 矩阵-向量乘法的代价 (高 → DRS)

最优实践: 从 DRS 开始快速原型 (参数少)，然后根据性能需求考虑 PDHG 优化。

## 来源

- Chambolle & Pock (2011): JMIV 40, 120-145
- O'Connor & Vandenberghe (2020): Math. Prog. 179, 85-108
- Pock & Chambolle (2011): ICCV 1762-1769
- Wang, Lan & Ye (2024): arXiv:2402.00311
- McManus et al. (2025): arXiv:2503.17575
- Giselsson & Boyd (2017): SIAM J. Optim. 27(2)
- Eckstein & Bertsekas (1992): Math. Prog. 55, 293-318
