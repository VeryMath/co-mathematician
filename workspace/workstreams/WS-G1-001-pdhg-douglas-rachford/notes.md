# 文献调研笔记：PDHG 与 Douglas-Rachford 对偶关系

## 1. 算法定义

### 1.1 Douglas-Rachford Splitting (DRS)

**问题**: min f(x) + g(x)，其中 f, g 为 proper convex l.s.c.

**迭代**:
```
x^{k+1} = prox_{γf}(z^k)
y^{k+1} = prox_{γg}(2x^{k+1} - z^k)   # 等价于 prox_{γg}(z^k) 如果从 z 视角
z^{k+1} = z^k + λ(y^{k+1} - x^{k+1})   # λ ∈ (0,2) 为松弛参数
```

等价于求解单调包含 0 ∈ ∂f(x) + ∂g(x)，即找到 x 使得 0 ∈ (A+B)(x)。

### 1.2 PDHG (Primal-Dual Hybrid Gradient)

**问题**: min_x f(Ax) + g(x)，等价于 min_x max_y ⟨Ax, y⟩ - f*(y) + g(x)

**迭代** (Chambolle-Pock 2011):
```
y^{k+1} = prox_{σf*}(y^k + σ A x̄^k)
x^{k+1} = prox_{τg}(x^k - τ A* y^{k+1})
x̄^{k+1} = x^{k+1} + θ(x^{k+1} - x^k)
```

收敛条件: τσ‖A‖² < 1, θ = 1 (或 θ ∈ [0,1])

## 2. 等价性证明（核心推导）

### 2.1 DRS ⊆ PDHG（已知方向）

令 A = I, τ = t, σ = 1/t, θ = 1，则 PDHG 退化为:
- y^{k+1} = prox_{f*/t}(y^k + (1/t)x̄^k)
- x^{k+1} = prox_{tg}(x^k - t y^{k+1})

通过 Moreau 分解 (prox_{f*/t}(z) = z - (1/t) prox_{tf}(tz))，可证明这等价于 DRS 应用于 f(x) + g(x)。

### 2.2 PDHG ⊆ DRS（O'Connor & Vandenberghe 2020 主要贡献）

**关键思路**: 将 PDHG 重新表述为 DRS 应用于一个特定构造的单调包含。

1. 原始问题 min_x f(Ax) + g(x) 的最优性条件:
   0 ∈ [0 Aᵀ; -A 0][x; y] + [∂g(x); ∂f*(y)]

2. 定义算子:
   T(u) = [Aᵀy; -Ax]  (斜对称算子)
   N(u) = [∂g(x); ∂f*(y)]

3. 则 PDHG 等价于 DRS 求解 0 ∈ (T+N)(u)

**Preconditioned Proximal Point 视角**: 引入对称正定矩阵 M = blkdiag(τ⁻¹I, σ⁻¹I - σAAᵀ)，则 PDHG 在 M-范数下等价于 DRS。

### 2.3 统一框架的意义

- PDHG 收敛性可直接从 DRS 理论导出
- 松弛参数 ρ ∈ (0,2) 在两个框架间直接对应
- 预条件 (τ, σ 矩阵化) 在 DRS 视角下更加自然

## 3. 收敛理论对比

### 3.1 一般凸情况

| 算法 | 速率 | 条件 |
|------|------|------|
| DRS | O(1/k) 遍历 | 一般凸 |
| PDHG | O(1/k) 遍历 | 一般凸, τσ‖A‖² < 1 |
| 加速 DRS | o(1/k) | 适当选择松弛参数 |

### 3.2 强凸情况 (线性收敛)

- DRS: min(f,g) 中至少一个强凸 + smooth → 线性 (Eckstein & Bertsekas 1992)
- PDHG: f* 或 g 强凸 → O(1/k²); 两者均强凸 → 线性
- Ozaslan & Jovanović (2024): 二次 + 非光滑 → 加速指数收敛

### 3.3 近年加速结果

- Cooling heuristics: 逐步增大松弛参数 → 实践中 o(1/k) (2024)
- 免调参 PDHG: 利用 DRS 等价性 + 非平稳 DRS 理论 → 自动参数选择 (Wang et al. 2024)

## 4. 实际选择指南

### 4.1 参数数量

- DRS: 2 个 (步长 γ, 松弛 λ)——更少参数，更易调参
- PDHG: 3 个 (τ, σ, θ)——更多参数，但灵活性更高

### 4.2 预备计算

- DRS: 需要 prox_f 和 prox_g
- PDHG: 需要 prox_g 和 prox_{f*} (Fenchel 共轭的邻近算子)

**选择关键**: 如果 f* 的 prox 比 f 的 prox 更容易计算 → PDHG

### 4.3 预条件

- PDHG: 天然支持对角线预条件 (Pock & Chambolle 2011)，无需计算全局 ‖A‖
- DRS: 预条件需要显式设计

### 4.4 数值实验证据

- **图像重建 (2024)**: SPDR > SPDHG (PSNR 更高、更稳定)
- **SDP (2024)**: 免调参 PDHG > 标准 PDHG
- **LASSO/TV 去噪 (2025)**: 松弛 PDHG + 线搜索 > 标准 PDHG

### 4.5 经验法则

1. 两个 prox 都好算 → DRS (简单)
2. 有自然 primal-dual 结构 (线性算子 A) → PDHG
3. 不想调参 → 免调参 PDHG (2024-2025)
4. 需要预条件 → PDHG
5. 大规模逆问题 → SPDR 或预条件 DRS

## 5. 开放问题和研究方向

- 一般非凸设置下的等价性
- 更高阶加速方法 (Nesterov 型) 在两个框架下的对应
- 随机变体的理论完备性
- 分布式/联邦学习场景中的应用

## 参考文献

- Chambolle & Pock (2011): JMIV 40, 120-145
- Condat (2013): JOTA 158(2), 460-479
- O'Connor & Vandenberghe (2020): Math. Prog. 179(1-2), 85-108
- Pock & Chambolle (2011): ICCV 1762-1769
- Wang, Lan & Ye (2024): arXiv:2402.00311
- McManus, Becker & Dwork (2025): arXiv:2503.17575
- Ozaslan & Jovanović (2024): arXiv:2407.20620
- Dong, Bredies & Sun (2024): arXiv:2212.13001
- Fercoq (2024): arXiv:2403.19202
- Goldstein et al. (2015): arXiv:1305.0546
