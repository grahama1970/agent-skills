cd /home/graham/workspace/experiments/pi-mono/.pi/skills/classifier-lab && \
./run.sh benchmark \
--data-dir /home/graham/workspace/experiments/pi-mono/.pi/skills/create-table-classifier/data/merge_images/split \
--modality vision \
--backbones convnextv2_nano.fcmae_ft_in22k_in1k \
--epochs 50 \
--lr 1e-04 \
--batch-size 16 \
--mixup-alpha 0.3 \
--cutmix-alpha 1.0 \
--random-erasing 0.2 \
--dropout 0.25 \
--weight-decay 0.001 \
--label-smoothing 0.1 \
--output-json /tmp/thunderdome-vision-convnext-long-r2.json \
--store-memory