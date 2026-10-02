# Next-best-action robustness: worlds where our assumptions are wrong

Share of the oracle's net incremental profit captured on 30,000 fresh leads (each world's true response). Models trained on 60,000 randomized decisions. *Best fixed* = the best of the six fixed policies in that world, chosen in hindsight. *Pick* = the family the closed loop's champion/challenger rule selected using only logged decisions (off-policy estimate on a 25% hold-out).

| World | Hidden share | Ours (interpretable) | Flexible (GBM) | Champion/challenger pick | Best fixed policy | Best fixed | Oracle ₹/1000 |
|---|---|---|---|---|---|---|---|
| documented | — | 92.1% | 85.5% | 92.1% (interpretable) | Email everyone (no discount) | 35.7% | 3,898,866 |
| null | — | ₹-16,331 | ₹-5,717 | ₹-16,331 | No contact | ₹0 | 0 |
| reversed | — | 70.2% | 54.7% | 70.2% (interpretable) | Email everyone (no discount) | 12.9% | 1,617,905 |
| hidden | — | 37.3% | 59.5% | 59.5% (flexible) | Email everyone (no discount) | 29.4% | 2,816,102 |
| random_01 | 0.52 | 68.2% | 60.7% | 60.7% (flexible) | No contact | 0.0% | 3,158,043 |
| random_02 | 0.71 | 74.5% | 79.1% | 79.1% (flexible) | 20% coupon to everyone | 13.8% | 4,020,587 |
| random_03 | 0.64 | 97.7% | 97.4% | 97.7% (interpretable) | Email everyone (no discount) | 97.0% | 6,896,027 |
| random_04 | 0.69 | 56.7% | 71.7% | 71.7% (flexible) | Email everyone (no discount) | 36.0% | 2,554,722 |
| random_05 | 0.84 | 73.6% | 90.4% | 90.4% (flexible) | Email everyone (no discount) | 64.5% | 5,121,855 |
| random_06 | 0.21 | 89.3% | 83.6% | 89.3% (interpretable) | Email everyone (no discount) | 54.1% | 4,636,466 |
| random_07 | 0.14 | 94.3% | 88.5% | 94.3% (interpretable) | Lead-score targeting (score-based CRM) | 0.5% | 3,386,415 |
| random_08 | 0.82 | 73.0% | 77.4% | 77.4% (flexible) | Lead-score targeting (score-based CRM) | 27.2% | 4,051,624 |
| random_09 | 0.58 | 89.0% | 92.0% | 92.0% (flexible) | Lead-score targeting (score-based CRM) | 53.3% | 7,161,810 |
| random_10 | 0.52 | 87.5% | 86.5% | 86.5% (flexible) | Lead-score targeting (score-based CRM) | 30.1% | 5,416,027 |
| random_11 | 0.13 | 98.5% | 96.6% | 98.5% (interpretable) | Email everyone (no discount) | 92.4% | 6,468,170 |
| random_12 | 0.50 | 72.4% | 62.9% | 72.4% (interpretable) | No contact | 0.0% | 2,728,146 |
| random_13 | 0.09 | 88.8% | 79.2% | 88.8% (interpretable) | No contact | 0.0% | 2,646,209 |
| random_14 | 0.44 | 91.6% | 87.6% | 91.6% (interpretable) | Email everyone (no discount) | 79.9% | 5,258,619 |
| random_15 | 0.13 | 95.4% | 89.7% | 95.4% (interpretable) | 20% coupon to everyone | 28.3% | 4,223,759 |
| random_16 | 0.48 | 77.1% | 79.5% | 77.1% (interpretable) | Lead-score targeting (score-based CRM) | 25.0% | 3,683,361 |
| random_17 | 0.11 | 90.7% | 87.1% | 87.1% (flexible) | No contact | 0.0% | 2,485,337 |
| random_18 | 0.60 | 72.2% | 61.0% | 72.2% (interpretable) | Email everyone (no discount) | 37.5% | 1,837,596 |
| random_19 | 0.44 | 80.0% | 79.1% | 80.0% (interpretable) | 20% coupon to everyone | 33.2% | 3,362,650 |
| random_20 | 0.67 | 61.3% | 61.2% | 61.3% (interpretable) | No contact | 0.0% | 2,599,503 |

**20 random worlds.** Beat the best fixed policy (chosen in hindsight): ours 20/20, flexible 20/20, champion/challenger 20/20. Median share of oracle profit: ours 83.8% (worst 56.7%), flexible 81.5% (worst 60.7%), champion/challenger 86.8% (worst 60.7%), best fixed 29.2%. The interpretable model beat the flexible one in 9/10 worlds with hidden share < 0.5 and 5/10 with hidden share ≥ 0.5 (correlation of hidden share with the interpretable model's advantage: -0.67). The champion/challenger rule picked the better family in 16/20.

## Named worlds — every policy (net incremental profit per 1,000 leads, ₹)

| Policy | documented | null | reversed | hidden |
|---|---|---|---|---|
| No contact | 0 | 0 | 0 | 0 |
| Email everyone (no discount) | 1,393,515 | -1,845 | 208,413 | 828,961 |
| 20% coupon to everyone | 553,592 | -2,970,517 | -2,117,084 | -1,548,872 |
| Random action | 1,037,883 | -872,290 | -471,120 | -17,305 |
| Tier playbook (rule-based workflow) | 902,443 | -785,403 | -348,209 | 86,833 |
| Lead-score targeting (score-based CRM) | 1,001,090 | -761,390 | -293,817 | 138,402 |
| Oracle (knows true effects) | 3,898,866 | 0 | 1,617,905 | 2,816,102 |
| Next-best-action (ours, interpretable) | 3,592,457 | -16,331 | 1,136,066 | 1,050,080 |
| Next-best-action (flexible GBM) | 3,332,422 | -5,717 | 885,590 | 1,676,363 |
| Next-best-action (champion/challenger pick) | 3,592,457 | -16,331 | 1,136,066 | 1,676,363 |

Null world: ours contacted 532 of every 1,000 leads (0 coupons, 100 calls).

## Learning curve (net profit per 1,000 leads vs number of randomized decisions)

| World | Decisions | Ours (interpretable) | Flexible (GBM) | Best fixed | Oracle |
|---|---|---|---|---|---|
| documented | 1,000 | 2,795,940 | 1,305,302 | 1,393,515 | 3,898,866 |
| documented | 3,000 | 3,217,012 | 1,683,828 | 1,393,515 | 3,898,866 |
| documented | 10,000 | 3,470,628 | 2,816,454 | 1,393,515 | 3,898,866 |
| documented | 30,000 | 3,572,444 | 3,199,734 | 1,393,515 | 3,898,866 |
| documented | 60,000 | 3,592,457 | 3,332,422 | 1,393,515 | 3,898,866 |
| hidden | 1,000 | 644,179 | 121,954 | 828,961 | 2,816,102 |
| hidden | 3,000 | 775,493 | 981,296 | 828,961 | 2,816,102 |
| hidden | 10,000 | 945,972 | 1,230,246 | 828,961 | 2,816,102 |
| hidden | 30,000 | 994,781 | 1,580,593 | 828,961 | 2,816,102 |
| hidden | 60,000 | 1,050,080 | 1,676,363 | 828,961 | 2,816,102 |
