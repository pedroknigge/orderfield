#!/usr/bin/env python3
"""Thin loader for tests.test_kernel.<Class> names used by of eval --kernel.

Discovery is delegated to test_kernel_{field,spec,pack,regime,cli}.py so
unittest collect does not double-run the split TestCase classes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from test_adapter_hints import AdapterHintsCli  # noqa: E402,F401
from test_claims_honesty import ClaimsHonestyGate  # noqa: E402,F401
from test_packaging import (  # noqa: E402,F401
    PackagingBumpDiscipline,
    ReadmeProductSurface,
    SkillLeaderInitiative,
)
from test_efficiency_signal import EfficiencySignalProof  # noqa: E402,F401
from test_kernel_cli import (  # noqa: E402,F401
    CliFieldResidual,
    DoctorOnePassSkew,
    DoctorSkillVersionSkew,
    MissionRewriteRefused,
    MultiHarnessResidual,
    UpdateAskDaily,
)
from test_kernel_field import (  # noqa: E402,F401
    DurableMultiDayResume,
    FieldAbandonedSignal,
    ClosedFieldArchiveTrail,
    OrphanPackedCleanup,
    PackedAgeWatchdog,
    ResumeAfterProcessDeath,
    ResumeRecoveryBrief,
    InFlightVisibility,
    MidEpicHandoffPacket,
    StatusReportJson,
    WaveRosterListShow,
)
from test_kernel_fields import (  # noqa: E402,F401
    NestedFieldLifecycle,
    PackRosterCrossField,
    RootStubAmbiguous,
)
from test_sibling_field_roundtrip import PackOutPhysicalNested  # noqa: E402,F401
from test_kernel_pack import (  # noqa: E402,F401
    SliceLintExplain,
    StalePackets,
    WaveReportQualityGate,
)
from test_kernel_spec import (  # noqa: E402,F401
    AdversarialDualTruthCorpus,
    CloseChecklistProof,
    ContrastDiffNarrative,
    ContrastReportRenderer,
    MultiWaveResidualLoop,
)

from test_kernel_regime import ThresholdStopSpawn  # noqa: E402,F401


def load_tests(loader, tests, pattern):
    # Re-exported eval TestCase classes must not be collected from this module.
    return loader.suiteClass()


if __name__ == "__main__":
    unittest.main()
