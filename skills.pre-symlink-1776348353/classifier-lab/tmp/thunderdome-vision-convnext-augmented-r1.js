--- a/run.sh
+++ b/run.sh
@@ -1,6 +1,6 @@
 #!/bin/bash
 ./run.sh benchmark --data-dir /home/graham/workspace/experiments/pi-mono/.pi/skills/create-table-classifier/data/merge_images/split \
   --modality vision --backbones convnextv2_nano.fcmae_ft_in22k_in1k --epochs 30 \
-  --lr 5e-05 --batch-size 16 --mixup-alpha 0.2 --cutmix-alpha 0.5 \
+  --lr 0.0001 --batch-size 32 --mixup-alpha 0.2 --cutmix-alpha 0.5 \
   --random-erasing 0.1 --dropout 0.15 --weight-decay 0.0005 \
   --label-smoothing 0.05 --output-json /tmp/thunderdome-vision-convnext-augmented-r1.json \
   --store-memory