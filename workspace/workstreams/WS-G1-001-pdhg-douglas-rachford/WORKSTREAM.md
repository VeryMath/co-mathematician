# 工作流：PDHG 与 Douglas-Rachford 对偶关系文献调研

- id: WS-G1-001-pdhg-douglas-rachford
- goal_id: G1
- kind: literature
- status: active

## 范围

系统梳理 PDHG 与 Douglas-Rachford splitting 的数学关系，重点关注等
价性证明、近年进展和实际算法选择指南。

## 关键文献

### 核心参考
- O'Connor & Vandenberghe (2020): "On the equivalence of the primal-dual hybrid gradient method and Douglas-Rachford splitting", Math. Prog., 179(1-2), 85-108.
- Chambolle & Pock (2011): 原始 PDHG 论文, JMIV 40, 120-145.
- Lions & Mercier (1979): DRS 原始论文
- Condat (2013): 首次注意到 DRS ⊆ PDHG

### 近年进展 (2020-2025)
- Fercoq (2024): 谱半径步长优化
- Goldstein et al. (2015): 残差平衡自适应步长
- Wang, Lan & Ye (2024): 免调参 PDHG (利用 DRS 等价性)
- McManus, Becker & Dwork (2025): 带线搜索的松弛 PDHG
- Ozaslan & Jovanovic (2024): 加速 DRS dynamics
- Dong, Bredies & Sun (2024): 随机预条件 DRS
- SPDR vs SPDHG (2024): 预条件 DRS 在图像重建中的数值比较

## 产出

- notes.md: 详细文献笔记
- artifacts/: 算法关系图、收敛速率对比表
- report.md: 文献综述报告
