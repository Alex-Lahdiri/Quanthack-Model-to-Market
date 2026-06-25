import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
cfg=[("mv_w480_g2",4.87),("mv_w480_g4",4.77),("iv_w480_s48_g2",3.36),("iv_w480_s48_g4",3.28),
("iv_w480_s12_g2",3.17),("iv_w480_s12_g4",3.14),("mv_w240_g4",2.98),("mv_w240_g2",2.95),
("iv_w240_s48_g4",1.41),("iv_w240_s48_g2",1.36),("iv_w240_s12_g4",-0.85),("iv_w240_s12_g2",-0.86),
("iv_w120_s48_g2",-4.56),("iv_w120_s48_g4",-4.63),("iv_w120_s12_g2",-7.05),("iv_w120_s12_g4",-7.17)]
names=[c[0] for c in cfg]; sr=[c[1] for c in cfg]
fig,ax=plt.subplots(figsize=(10,5))
ax.bar(range(len(sr)),sr,color=["#2e7d32" if "mv" in n else "#5b8db8" for n in names])
ax.axhline(7.38,ls="--",color="#c0392b",label="expected max under null, N=16 trials (7.4)")
ax.axhline(9.34,ls=":",color="#c0392b",label="N=50 trials (9.3)")
ax.set_xticks(range(len(names))); ax.set_xticklabels(names,rotation=90,fontsize=7)
ax.set_ylabel("annualized Sharpe"); ax.axhline(0,color="k",lw=.5)
ax.set_title("Deflated Sharpe: best backtest (4.9) sits BELOW the luck threshold (7.4)\nDSR=0.26 (fails) | PBO=21% (ranking moderately persistent)")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig("results/research/overfit_dsr.png",dpi=120)
print("saved overfit_dsr.png")
