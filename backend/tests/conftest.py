import pytest

from tests.fixtures.make_dxf import (make_arch_dxf, make_elec_dxf, make_foundation_dxf, make_beam_detail_dxf, make_facade_dxf, make_network_dxf, make_rebar_table_dxf,
                                     make_standard_dxf, make_storey_dxf, make_unitless_mm_dxf)


@pytest.fixture(scope="session")
def network_dxf(tmp_path_factory):
    return make_network_dxf(tmp_path_factory.mktemp("dxf") / "ag.dxf")


@pytest.fixture(scope="session")
def storey_dxf(tmp_path_factory):
    return make_storey_dxf(tmp_path_factory.mktemp("dxf") / "kat.dxf")


@pytest.fixture(scope="session")
def foundation_dxf(tmp_path_factory):
    return make_foundation_dxf(tmp_path_factory.mktemp("dxf") / "temel.dxf")


@pytest.fixture(scope="session")
def unitless_dxf(tmp_path_factory):
    return make_unitless_mm_dxf(tmp_path_factory.mktemp("dxf") / "mm.dxf")


@pytest.fixture(scope="session")
def arch_dxf(tmp_path_factory):
    return make_arch_dxf(tmp_path_factory.mktemp("dxf") / "mimari.dxf")


@pytest.fixture(scope="session")
def elec_dxf(tmp_path_factory):
    return make_elec_dxf(tmp_path_factory.mktemp("dxf") / "elektrik.dxf")


@pytest.fixture(scope="session")
def standard_dxf(tmp_path_factory):
    return make_standard_dxf(tmp_path_factory.mktemp("dxf") / "ksf.dxf")


@pytest.fixture(scope="session")
def rebar_dxf(tmp_path_factory):
    return make_rebar_table_dxf(tmp_path_factory.mktemp("dxf") / "donati.dxf")


@pytest.fixture(scope="session")
def beam_detail_dxf(tmp_path_factory):
    return make_beam_detail_dxf(tmp_path_factory.mktemp("dxf") / "kiris_detay.dxf")


@pytest.fixture(scope="session")
def facade_dxf(tmp_path_factory):
    return make_facade_dxf(tmp_path_factory.mktemp("dxf") / "cephe.dxf")


@pytest.fixture(scope="session")
def roof_dxf(tmp_path_factory):
    from tests.fixtures.make_dxf import make_roof_dxf
    return make_roof_dxf(tmp_path_factory.mktemp("dxf") / "cati.dxf")
