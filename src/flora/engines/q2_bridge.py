"""Run QIIME 2 + DADA2 through the QIIME 2 **Python API**.

This file is executed with the Python interpreter of the QIIME 2 environment (not FLORA's), so it imports nothing
from FLORA: it only needs the standard library and ``qiime2``. Usage: ``python q2_bridge.py spec.json``.

It writes the same ``export/`` layout as the CLI workflow, so FLORA converts both identically:
``export/table/feature-table.biom``, ``export/rep-seqs/``, ``export/taxonomy/taxonomy.tsv`` and ``export/tree/tree.nwk``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def log(message: str) -> None:
    print(message, flush=True)


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text("utf-8"))
    out = Path(spec["out"])
    export = out / "export"
    params = spec.get("params", {})
    paired = bool(spec.get("paired", True))

    from qiime2 import Artifact
    from qiime2.plugins import dada2

    log("[1/4] importando o manifest")
    kind = "SampleData[PairedEndSequencesWithQuality]" if paired else "SampleData[SequencesWithQuality]"
    view = "PairedEndFastqManifestPhred33V2" if paired else "SingleEndFastqManifestPhred33V2"
    demux = Artifact.import_data(kind, spec["manifest"], view_type=view)

    log("[2/4] DADA2 (denoise-%s)" % ("paired" if paired else "single"))
    threads = int(spec.get("threads", 1))
    if paired:
        result = dada2.methods.denoise_paired(
            demultiplexed_seqs=demux, n_threads=threads,
            trim_left_f=int(params.get("trim_left_f", 0)), trunc_len_f=int(params.get("trunc_len_f", 0)),
            trim_left_r=int(params.get("trim_left_r", 0)), trunc_len_r=int(params.get("trunc_len_r", 0)),
        )
    else:  # denoise_single has no _f/_r suffixes
        result = dada2.methods.denoise_single(
            demultiplexed_seqs=demux, n_threads=threads,
            trim_left=int(params.get("trim_left_f", 0)), trunc_len=int(params.get("trunc_len_f", 0)),
        )
    result.table.export_data(str(export / "table"))
    result.representative_sequences.export_data(str(export / "rep-seqs"))
    result.denoising_stats.export_data(str(export / "denoising-stats"))

    if spec.get("classifier"):
        log("[3/4] classificando a taxonomia")
        from qiime2.plugins import feature_classifier

        classifier = Artifact.load(spec["classifier"])
        taxonomy = feature_classifier.methods.classify_sklearn(reads=result.representative_sequences, classifier=classifier).classification
        taxonomy.export_data(str(export / "taxonomy"))
    else:
        log("[3/4] sem classificador: taxonomia ignorada")

    if spec.get("build_tree"):
        log("[4/4] construindo a árvore filogenética")
        from qiime2.plugins import phylogeny

        tree = phylogeny.pipelines.align_to_tree_mafft_fasttree(sequences=result.representative_sequences)
        tree.rooted_tree.export_data(str(export / "tree"))
    else:
        log("[4/4] sem árvore")
    log("concluído")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python q2_bridge.py spec.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
