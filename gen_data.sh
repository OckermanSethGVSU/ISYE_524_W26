for i in 0 1 2 3; do
    OUTDIR="level${i}data"

    # remove old directory if it exists
    rm -rf "$OUTDIR"

    # regenerate data
    python3 generate_supply_chain_data.py \
        --output-dir "$OUTDIR" \
        --seed 2 \
        --customers 4 \
        --local-shops 4 \
        --regional-warehouses 2 \
        --visualize \
        --components 32 \
        --complexity "$i" \
        --visualization-layout separate
done