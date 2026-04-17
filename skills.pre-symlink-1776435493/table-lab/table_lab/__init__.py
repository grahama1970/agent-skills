"""table-lab: Iterative Camelot parameter tuning for table extraction.

Samples pages from a PDF, tries different Camelot settings, evaluates
fragmentation and cell counts, and converges on optimal parameters.
Stores results as hint files that S05 reads at extraction time.
"""
