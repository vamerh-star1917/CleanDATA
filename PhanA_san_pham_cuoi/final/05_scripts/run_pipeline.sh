#!/usr/bin/env bash
# Dựng lại TOÀN BỘ dữ liệu phần A từ hai tệp gốc. Cách dùng: bash run_pipeline.sh <thư mục chứa 2 tệp jsonl>
# Cần: python3, pandas, numpy, scipy, scikit-learn, matplotlib, openpyxl. Mỗi lần chạy cho kết quả giống hệt (seed cố định).
set -euo pipefail
RAW="${1:?Cần đường dẫn thư mục chứa shopee_reviews_dataset.jsonl và aug_unaccented_reviews.jsonl}"
cd "$(dirname "$0")"
mkdir -p ../01_data ../02_scenarios ../03_prompt ../04_labeling ../06_reports ../_tmp
python3 clean_data.py --main "$RAW/shopee_reviews_dataset.jsonl" --aug "$RAW/aug_unaccented_reviews.jsonl" --out ../_tmp/clean > /dev/null
cp ../_tmp/clean/shopee_clean.csv ../01_data/shopee_clean.csv
cp ../_tmp/clean/cleaning_log.json ../_tmp/clean/crosstab_rating_label.csv ../_tmp/clean/rating_label_disagreements.csv ../06_reports/
python3 build_splits.py --clean ../01_data/shopee_clean.csv --aug "$RAW/aug_unaccented_reviews.jsonl" --out ../01_data --report-dir ../06_reports > /dev/null
python3 build_prompts.py --fewshot ../03_prompt/fewshot_examples.json --gold ../01_data/review_gold.csv --out ../03_prompt > /dev/null
python3 build_scenarios.py --master ../01_data/reviews.csv --gold ../01_data/review_gold.csv --fewshot ../03_prompt/fewshot_examples.json --out ../02_scenarios > /dev/null
python3 build_preload_sql.py > /dev/null
python3 verify_preload.py > /dev/null
python3 evaluate.py --out ../06_reports > /dev/null          # baseline số sao (chưa có dự đoán Gemini)
python3 make_labeling_sheets.py --out ../04_labeling > /dev/null
python3 build_data_dictionary.py > /dev/null
python3 make_data_report.py
rm -rf ../_tmp
echo "Xong. Kiểm tra 06_reports/bao_cao_kiem_tra_du_lieu.md"
