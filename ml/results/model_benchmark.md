# Our lead-scoring method on real data (9,240 real X Education leads, 9 leak-free columns)

5-fold cross-validation x 3 seeds (mean ± sd). Lower log-loss / Brier / calibration error is better.

| Model | AUC | Log-loss | Brier | Calibration error | Bought among the top 10% |
|---|---|---|---|---|---|
| Boosting + neural network, averaged | 0.875 ± 0.000 | 0.4258 ± 0.0005 | 0.1354 | 0.013 | 94.9% |
| Gradient boosting | 0.874 ± 0.001 | 0.4265 ± 0.0009 | 0.1357 | 0.009 | 94.5% |
| Random forest | 0.875 ± 0.001 | 0.4314 ± 0.0006 | 0.1367 | 0.040 | 94.8% |
| Neural network, 2 hidden layers (64-32) | 0.868 ± 0.001 | 0.4369 ± 0.0024 | 0.1394 | 0.019 | 94.5% |
| Neural network, 3 hidden layers (128-64-32) | 0.867 ± 0.002 | 0.4379 ± 0.0025 | 0.1400 | 0.015 | 94.2% |
| Neural network, calibrated | 0.868 ± 0.000 | 0.4436 ± 0.0009 | 0.1393 | 0.013 | 94.3% |
| Logistic regression | 0.838 ± 0.000 | 0.4798 ± 0.0001 | 0.1558 | 0.037 | 91.7% |

TabPFN was not installed here, so it is not in the table (pip install tabpfn to add it).

For contrast — gradient boosting WITH the post-contact columns (Tags, Lead Quality, Last Notable Activity, Last Activity, Lead Profile): AUC 0.980, accuracy 94.2%. Those columns are written by sales after contacting the lead, so a new lead never has them: that number cannot be reached in real use.

The CRM's own base model (trained only on simulated leads) applied to these real leads as they are: AUC 0.612, average predicted chance 7.6% vs 38.5% who actually bought. The real file has none of the website signals (video, pricing, cart, checkout ...) the model mostly relies on, so it cannot be judged on this file. In the running CRM every lead has those signals, and the learning loop corrects the base model from the CRM's own outcomes, checked on the untouched control group.
