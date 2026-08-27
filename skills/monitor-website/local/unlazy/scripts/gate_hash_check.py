import hashlib
paths=['docs/assets/project-cards/memory-recall-card.svg','site/public/projects/memory-recall-card.svg','site/public/projects/thumbs/memory-recall-card.svg','site/out/projects/memory-recall-card.svg','site/out/projects/thumbs/memory-recall-card.svg']
h={hashlib.sha256(open(p,'rb').read()).hexdigest() for p in paths}
print('INSTALL_UNIFORM_OK' if len(h)==1 else 'INSTALL_DRIFT '+str(h))
