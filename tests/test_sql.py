from io import StringIO
import json
import networkx as nx
from psycopg2.extras import DictCursor
import freezegun
import pytest
import dbtool

from portfoliograph.landlord_index import (
    get_corpname_data_for_algolia,
    get_landlord_data_for_algolia,
    dict_hash,
)

from .factories.hpd_contacts import HpdContacts
from .factories.hpd_registrations import HpdRegistrations
from .factories.hpd_complaints import HpdComplaints
from .factories.hpd_complaint_problems import HpdComplaintProblems
from .factories.dof_exemptions import DofExemptions
from .factories.dof_exemption_classification_codes import (
    DofExemptionClassificationCodes,
)
from .factories.marshal_evictions_17 import MarshalEvictions17
from .factories.marshal_evictions_18 import MarshalEvictions18
from .factories.marshal_evictions_19 import MarshalEvictions19
from .factories.marshal_evictions_all import MarshalEvictionsAll
from .factories.oca_evictions_bldgs import OcaEvictionsBldgs
from .factories.oca_evictions_monthly import OcaEvictionsMonthly
from .factories.nycha_bbls_18 import NychaBbls18
from .factories.changes_summary import ChangesSummary
from .factories.hpd_violations import HpdViolations
from .factories.dob_violations import DobViolations
from .factories.ecb_violations import EcbViolations
from .factories.pluto_latest import PlutoLatest
from .factories.real_property_master import RealPropertyMaster
from .factories.real_property_legals import RealPropertyLegals

from portfoliograph.graph import (
    build_graph,
    Node,
    NodeKind,
)
from portfoliograph.table import populate_portfolios_table, export_portfolios_table_json
from ocaevictions.table import OcaConfig, create_oca_tables, populate_oca_tables

# This test suite defines two landlords:
#
# * CLOUD CITY MEGAPROPERTIES is a landlord with
#   three buildings in its portfolio, FUNKY, MONKEY,
#   and SPUNKY. FUNKY is hidden behind an LLC but
#   the association can be inferred from its business
#   address, while SPUNKY has a head officer whose
#   name is spelled slightly differently from MONKEY's.
#
# * THE UNRELATED COMPANIES, L.P. is a landlord with
#   one building, UNRELATED.

FUNKY_BBL = "3000010002"

MONKEY_BBL = "3000040005"

SPUNKY_BBL = "3000040006"

UNRELATED_BBL = "1000010002"

FUNKY_REGISTRATION = HpdRegistrations(
    RegistrationID="1",
    HouseNumber="1",
    StreetName="FUNKY STREET",
    BoroID="3",
    Block="1",
    Lot="2",
)

MONKEY_REGISTRATION = HpdRegistrations(
    RegistrationID="2",
    HouseNumber="2",
    StreetName="MONKEY STREET",
    BoroID="3",
    Block="4",
    Lot="5",
)

SPUNKY_REGISTRATION = HpdRegistrations(
    RegistrationID="4",
    HouseNumber="4",
    StreetName="SPUNKY STREET",
    BoroID="3",
    Block="4",
    Lot="6",
)

UNRELATED_REGISTRATION = HpdRegistrations(
    RegistrationID="3",
    HouseNumber="3",
    StreetName="UNRELATED STREET",
    BoroID="1",
    Block="1",
    Lot="2",
)

FUNKY_CONTACT = HpdContacts(
    RegistrationID="1",
    Type="HeadOfficer",
    FirstName="Lobot",
    LastName="Jones",
    CorporationName="1 FUNKY STREET LLC",
    BusinessHouseNumber="5",
    BusinessStreetName="BESPIN AVE",
    BusinessZip="11231",
)

MONKEY_CONTACT = HpdContacts(
    RegistrationID="2",
    Type="HeadOfficer",
    FirstName="Landlordo",
    LastName="Calrissian",
    CorporationName="CLOUD CITY MEGAPROPERTIES",
    BusinessHouseNumber="5",
    BusinessStreetName="BESPIN AVE",
    BusinessZip="11231",
)

SPUNKY_CONTACT = HpdContacts(
    RegistrationID="4",
    Type="HeadOfficer",
    FirstName="Landlordo",
    LastName="Calrisian",
    CorporationName="4 SPUNKY STREET LLC",
    BusinessHouseNumber="700",
    BusinessStreetName="SUPERSPUNKY AVE",
    BusinessZip="11201",
)

UNRELATED_CONTACT = HpdContacts(
    RegistrationID="3",
    Type="HeadOfficer",
    FirstName="Boop",
    LastName="Jones",
    CorporationName="THE UNRELATED COMPANIES, L.P.",
    BusinessHouseNumber="6",
    BusinessStreetName="UNRELATED AVE",
    BusinessZip="11231",
)


class TestOcaTableBuild:
    def test_oca_table_empty_if_no_creds(self, db, capsys):

        config = OcaConfig(
            oca_table_names=["oca_evictions_bldgs"],
            sql_dir=dbtool.SQL_DIR,
            # Confusingly, we need to say we aren't testing and use the test
            # data directory to properly test that a user can still do a real
            # build even without OCA creds
            data_dir=dbtool.ROOT_DIR / "tests" / "data",
            test_dir=dbtool.ROOT_DIR / "tests" / "data",
            is_testing=False,
        )
        with db.cursor() as cur:
            create_oca_tables(cur, config)
            populate_oca_tables(cur, config)
            captured = capsys.readouterr()
            assert "Leaving tables empty" in captured.out
            cur.execute("select count(*) as rows from oca_evictions_bldgs")
            r = cur.fetchone()
            cur.execute("drop table oca_evictions_bldgs")
        assert r["rows"] == 0


class TestSQL:
    @pytest.fixture(autouse=True, scope="class")
    def setup_class_fixture(self, db, nycdb_ctx):
        nycdb_ctx.write_csv("pluto_latest.csv", [PlutoLatest()])
        nycdb_ctx.write_csv("hpd_violations.csv", [HpdViolations()])
        nycdb_ctx.write_csv("hpd_complaints.csv", [HpdComplaints()])
        nycdb_ctx.write_csv("dob_violations.csv", [DobViolations()])
        nycdb_ctx.write_csv("ecb_violations.csv", [EcbViolations()])
        nycdb_ctx.write_csv("dof_exemptions.csv", [DofExemptions()])
        nycdb_ctx.write_csv(
            "dof_exemption_classification_codes.csv",
            [DofExemptionClassificationCodes()],
        )
        nycdb_ctx.write_csv("hpd_complaint_problems.csv", [HpdComplaintProblems()])
        nycdb_ctx.write_csv("changes-summary.csv", [ChangesSummary()])
        nycdb_ctx.write_csv("marshal_evictions_17.csv", [MarshalEvictions17()])
        nycdb_ctx.write_csv("marshal_evictions_18.csv", [MarshalEvictions18()])
        nycdb_ctx.write_csv("marshal_evictions_19.csv", [MarshalEvictions19()])
        nycdb_ctx.write_csv("marshal_evictions_all.csv", [MarshalEvictionsAll()])
        nycdb_ctx.write_csv("oca_evictions_bldgs.csv", [OcaEvictionsBldgs()])
        nycdb_ctx.write_csv("oca_evictions_monthly.csv", [OcaEvictionsMonthly()])
        nycdb_ctx.write_csv("nycha_bbls_18.csv", [NychaBbls18()])
        nycdb_ctx.write_csv("real_property_master.csv", [RealPropertyMaster()])
        nycdb_ctx.write_csv("real_property_legals.csv", [RealPropertyLegals()])
        nycdb_ctx.write_csv(
            "hpd_registrations.csv",
            [
                FUNKY_REGISTRATION,
                MONKEY_REGISTRATION,
                SPUNKY_REGISTRATION,
                UNRELATED_REGISTRATION,
            ],
        )
        nycdb_ctx.write_csv(
            "hpd_contacts.csv",
            [FUNKY_CONTACT, MONKEY_CONTACT, SPUNKY_CONTACT, UNRELATED_CONTACT],
        )
        nycdb_ctx.build_everything()

    @pytest.fixture(autouse=True)
    def setup_fixture(self, db):
        self.db = db

    def query_one(self, query):
        results = self.query_all(query)
        assert len(results) == 1
        return results[0]

    def query_all(self, query):
        with self.db.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()

    def get_assoc_addrs_from_bbl(self, bbl, expected_bbls=None):
        results = self.query_all(f"SELECT * FROM get_assoc_addrs_from_bbl('{bbl}')")
        results_by_bbl = {}
        for result in results:
            results_by_bbl[result["bbl"]] = result
        if expected_bbls is not None:
            assert set(results_by_bbl.keys()) == set(expected_bbls)
        return results_by_bbl

    def test_oca_bldg_table_populated(self):
        r = self.query_one(f"SELECT * FROM oca_evictions_bldgs WHERE bbl='1000087501'")
        assert r["eviction_filings_since_2017"] == 10

    def test_oca_monthly_table_populated(self):
        r = self.query_one(
            f"SELECT * FROM oca_evictions_monthly WHERE bbl='1000087501'"
        )
        assert r["month"] == "2016-02"
        assert r["evictionfilings"] == 1

    def test_wow_bldgs_is_populated(self):
        r = self.query_one(f"SELECT * FROM wow_bldgs WHERE bbl='{FUNKY_BBL}'")
        assert r["housenumber"] == "1"
        assert r["streetname"] == "FUNKY STREET"
        assert r["businessaddrs"] == ["5 BESPIN AVENUE 11231"]

    def test_get_assoc_addrs_from_bbl_returns_one_building_porfolios(self):
        assert len(self.get_assoc_addrs_from_bbl(UNRELATED_BBL)) == 1

    def test_get_assoc_addrs_from_bbl_returns_empty_set_on_invalid_bbl(self):
        assert len(self.get_assoc_addrs_from_bbl("zzz")) == 0

    def test_get_assoc_addrs_from_bbl_links_buildings_through_businessaddrs_and_names(
        self,
    ):
        self.get_assoc_addrs_from_bbl(
            MONKEY_BBL,
            expected_bbls=[
                # This includes all the buildings in the portfolio because MONKEY shares
                # the same (fuzzy) head officer name as SPUNKY and the exact same address
                # as FUNKY.
                FUNKY_BBL,
                MONKEY_BBL,
                SPUNKY_BBL,
            ],
        )

        self.get_assoc_addrs_from_bbl(
            FUNKY_BBL,
            expected_bbls=[
                # Ideally this should include SPUNKY, but because the head officer of FUNKY is
                # completely unrelated to the head officer of SPUNKY and they also don't
                # share the exact same address, that connection can't be inferred.
                #
                # In other words, get_assoc_addrs_from_bbl() doesn't currently support
                # transitivity: just because MONKEY is associated with FUNKY and
                # MONKEY is associated with SPUNKY does *not* mean that
                # FUNKY is associated with SPUNKY (even though it should be).
                FUNKY_BBL,
                MONKEY_BBL,
            ],
        )

        self.get_assoc_addrs_from_bbl(
            SPUNKY_BBL,
            expected_bbls=[
                # For similar reasons, this should ideally include FUNKY but doesn't.
                SPUNKY_BBL,
                MONKEY_BBL,
            ],
        )

    def test_get_assoc_addrs_from_bbl_has_expected_strucure(self):
        funky = self.get_assoc_addrs_from_bbl(FUNKY_BBL)[FUNKY_BBL]
        assert funky["housenumber"] == "1"
        assert funky["streetname"] == "FUNKY STREET"
        assert funky["businessaddrs"] == ["5 BESPIN AVENUE 11231"]

    def test_hpd_registrations_with_contacts_is_populated(self):
        r = self.query_one(
            f"SELECT * FROM hpd_registrations_with_contacts WHERE bbl='{FUNKY_BBL}'"
        )
        assert r["registrationid"] == 1
        assert r["housenumber"] == "1"
        assert r["streetname"] == "FUNKY STREET"
        assert r["corpnames"] == ["1 FUNKY STREET LLC"]
        assert r["businessaddrs"] == ["5 BESPIN AVENUE 11231"]
        assert r["ownernames"] == [
            {
                "title": "HeadOfficer",
                "value": "Lobot Jones",
            }
        ]
        assert r["allcontacts"] == [
            {
                "title": "HeadOfficer",
                "value": "Lobot Jones",
                "address": {
                    "zip": "11231",
                    "city": "BROKLYN",
                    "state": "NY",
                    "apartment": None,
                    "streetname": "BESPIN AVENUE",
                    "housenumber": "5",
                },
            },
            {
                "title": "Corporation",
                "value": "1 FUNKY STREET LLC",
                "address": {
                    "zip": "11231",
                    "city": "BROKLYN",
                    "state": "NY",
                    "apartment": None,
                    "streetname": "BESPIN AVENUE",
                    "housenumber": "5",
                },
            },
        ]

    def test_built_graph_works(self):
        with self.db.connect() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            with freezegun.freeze_time("2018-01-01"):
                g = build_graph(cur)
            assert set(g.nodes) == {
                Node(kind=NodeKind.NAME, value="BOOP JONES"),
                Node(kind=NodeKind.BIZADDR, value="6 UNRELATED AVENUE, BROKLYN NY"),
                Node(kind=NodeKind.NAME, value="LANDLORDO CALRISIAN"),
                Node(kind=NodeKind.NAME, value="LANDLORDO CALRISSIAN"),
                Node(kind=NodeKind.BIZADDR, value="5 BESPIN AVENUE, BROKLYN NY"),
                Node(kind=NodeKind.NAME, value="LOBOT JONES"),
                Node(kind=NodeKind.BIZADDR, value="700 SUPERSPUNKY AVENUE, BROKLYN NY"),
            }
            assert len(list(nx.connected_components(g))) == 3

    def test_portfolio_graph_works(self):
        # This test has side effect from populate_portfolios_table
        with self.db.connect() as conn:
            with freezegun.freeze_time("2018-01-01"):
                populate_portfolios_table(conn)
        r = self.query_one(
            "SELECT landlord_names FROM wow_portfolios WHERE '"
            + FUNKY_BBL
            + "' = any(bbls)"
        )
        assert set(r[0]) == {"LANDLORDO CALRISSIAN", "LOBOT JONES"}

    def test_getting_landlord_names_for_algolia_index(self):
        with self.db.connect() as conn:
            with freezegun.freeze_time("2018-01-01"):
                r = get_landlord_data_for_algolia(conn, 20)
                assert len(r) == 4

                # The result is a list of dicts, and each dict includes the ObjectID, which
                # is the hash of the rest of the dict. To simplify the expected data testing
                # we remove all those objectIDs and test those separately first before checking
                # the rest of the contents
                r_hashes = []
                for row in r:
                    r_hashes.append(row.pop("objectID"))
                assert r_hashes[0] == dict_hash(r[0])

                assert {
                    "portfolio_bbl": "1000010002",
                    "landlord_names": "BOOP JONES",
                } in r
                assert {
                    "portfolio_bbl": "3000040006",
                    "landlord_names": "LANDLORDO CALRISIAN",
                } in r
                assert {
                    "portfolio_bbl": "3000010002",
                    "landlord_names": "LOBOT JONES",
                } in r
                assert {
                    "portfolio_bbl": "3000010002",
                    "landlord_names": "LANDLORDO CALRISSIAN",
                } in r

                r2 = get_landlord_data_for_algolia(conn)
                assert len(r2) == 3

                r2_hashes = []
                for row in r2:
                    r2_hashes.append(row.pop("objectID"))
                assert r2_hashes[0] == dict_hash(r2[0])

                assert {
                    "portfolio_bbl": "1000010002",
                    "landlord_names": "BOOP JONES",
                } in r2
                assert {
                    "portfolio_bbl": "3000040006",
                    "landlord_names": "LANDLORDO CALRISIAN",
                } in r2
                assert {
                    "portfolio_bbl": "3000010002",
                    "landlord_names": "LANDLORDO CALRISSIAN, LOBOT JONES",
                } in r2

    def test_getting_corporation_names_for_algolia_index(self):
        with self.db.connect() as conn:
            with freezegun.freeze_time("2018-01-01"):
                r = get_corpname_data_for_algolia(conn)
                assert len(r) == 4

                # The result is a list of dicts, and each dict includes the ObjectID, which
                # is the hash of the rest of the dict. To simplify the expected data testing
                # we remove all those objectIDs and test those separately first before checking
                # the rest of the contents
                r_hashes = []
                for row in r:
                    r_hashes.append(row.pop("objectID"))
                assert r_hashes[0] == dict_hash(r[0])

                assert {
                    "portfolio_bbl": "1000010002",
                    "landlord_names": "THE UNRELATED COMPANIES, L.P.",
                } in r
                assert {
                    "portfolio_bbl": "3000010002",
                    "landlord_names": "1 FUNKY STREET LLC",
                } in r
                assert {
                    "portfolio_bbl": "3000040005",
                    "landlord_names": "CLOUD CITY MEGAPROPERTIES",
                } in r
                assert {
                    "portfolio_bbl": "3000040006",
                    "landlord_names": "4 SPUNKY STREET LLC",
                } in r

    def test_portfolio_graph_json_works(self):
        with self.db.connect() as conn:
            f = StringIO()
            with freezegun.freeze_time("2018-01-01"):
                export_portfolios_table_json(conn, f)

            # Ideally we'd actually do a snapshot test here,
            # but I'm not confident that the ordering of
            # lists will be deterministic, so for now we'll
            # just leave it as a smoke test... -AV
            json.loads(f.getvalue())
