for i in 0 1 2 3; do
    DATADIR="level${i}data"
    OUTDIR="level${i}output"

    
    
    python3 visualize_solution.py --data-dir $DATADIR \
    --output-dir $OUTDIR 
    
    python3 visualize_solution.py --data-dir $DATADIR \
    --output-dir $OUTDIR --per-component

    python3 visualize_solution.py --data-dir $DATADIR \
    --output-dir $OUTDIR \
    --family-root LRU_2 --image-file solution_family_lru_2.png --summary-file solution_family_lru_2.md

    if [[ $i -eq 3 ]]; then
        python3 visualize_solution.py --data-dir level3data --output-dir level3output \
        --image-file level3Summary.png --summary-file level3summary.md --per-timestep
    fi


done


DATADIR="level3data"
OUTDIR="level3_5output"
   
python3 visualize_solution.py --data-dir $DATADIR \
--output-dir $OUTDIR 

python3 visualize_solution.py --data-dir $DATADIR \
--output-dir $OUTDIR --per-component

python3 visualize_solution.py --data-dir $DATADIR \
--output-dir $OUTDIR \
--family-root LRU_2 --image-file solution_family_lru_2.png --summary-file solution_family_lru_2.md

python3 visualize_solution.py --data-dir level3data --output-dir level3_5output \
    --image-file level3_5Summary.png --summary-file level3_5summary.md --per-timestep