"""Fase 2 — stabilitets-/smoothing-logik.

Modtager en strøm af (KeyResult eller None) og afgør hvornår en toneart er
"stabil" nok til at rapportere/sende. Undgår flapper mellem to nærliggende toner.

Regel: en kandidat bliver stabil når samme relative_major_pc er detekteret med
confidence >= threshold i nok på hinanden følgende vinduer. Vi smoother på
relative_major_pc (det vi faktisk sender via CC#16) — ikke på mode — så
E-mol/G-dur-forveksling ikke tæller som ustabilitet.

ASYMMETRISK anti-flap: FØRSTE lås (intet committet endnu) kræver kun
`stable_windows_required` vinduer (hurtig — autotune paa fra foerste frase). At
SKIFTE væk fra en allerede låst key kræver `change_windows_required` (flere) ens
vinduer, saa spuriøse kandidater under usikker detektion ikke flapper CC#16.
"""
from collections import deque
from dataclasses import dataclass


@dataclass
class StableKey:
    relative_major_pc: int
    key: str
    mode: str
    confidence: float


class Smoother:
    def __init__(self, stable_windows_required=3, confidence_threshold=0.45,
                 change_windows_required=None):
        self.required = stable_windows_required
        # Skift kræver flere ens vinduer end første lås (anti-flap). Default: +2, min 4.
        self.change_required = int(change_windows_required) if change_windows_required \
            else max(stable_windows_required + 2, 4)
        self.threshold = confidence_threshold
        self.recent = deque(maxlen=max(self.required, self.change_required))
        self.current_stable = None  # relative_major_pc der pt. er committet

    def update(self, result):
        """result: KeyResult eller None (for lavt niveau/usikkert).

        Returnerer StableKey hvis et NYT stabilt skifte netop blev bekræftet,
        ellers None.
        """
        if result is None or result.confidence < self.threshold:
            self.recent.append(None)
            return None

        self.recent.append(result)
        # Første lås: hurtig. Skift væk fra committet key: kræv flere ens vinduer.
        need = self.required if self.current_stable is None else self.change_required
        pcs = [r.relative_major_pc for r in self.recent if r is not None]
        if len(pcs) < need:
            return None
        last = pcs[-need:]
        if all(pc == last[-1] for pc in last):
            pc = last[-1]
            if pc != self.current_stable:
                self.current_stable = pc
                r = self.recent[-1]
                return StableKey(pc, r.key, r.mode, r.confidence)
        return None

    def reset(self):
        self.recent.clear()
        self.current_stable = None
