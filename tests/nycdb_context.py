import os
from pathlib import Path
from types import SimpleNamespace
from io import StringIO
import csv
import zipfile
import tempfile
import nycdb

import dbtool
from .generate_factory_from_csv import unmunge_colname
from ocaevictions.table import OcaConfig, create_oca_tables, populate_oca_tables

if "TEST_DATABASE_URL" in os.environ:
    TEST_DB_URL = os.environ["TEST_DATABASE_URL"]
else:
    TEST_DB_URL = os.environ["DATABASE_URL"] + "_test"

TEST_DB = dbtool.DbContext.from_url(TEST_DB_URL)


class NycdbContext:
    """
    An object facilitating interactions with NYCDB from tests.
    """

    def __init__(self, root_dir, get_cursor):
        self.args = SimpleNamespace(
            user=TEST_DB.user,
            password=TEST_DB.password,
            host=TEST_DB.host,
            database=TEST_DB.database,
            port=TEST_DB.port,
            root_dir=root_dir,
            hide_progress=False,
        )
        self.oca_config = OcaConfig(
            oca_table_names=dbtool.WOW_YML["oca_tables"],
            data_dir=Path(root_dir),
            # using main location since test files are copied there
            test_dir=Path(root_dir),
            sql_dir=dbtool.SQL_DIR,
            is_testing=True,
        )
        self.root_dir = Path(root_dir)
        self.get_cursor = get_cursor

    def load_dataset(self, name: str):
        """Load the given NYCDB dataset into the database."""

        nycdb.Dataset(name, args=self.args).db_import()

    def _write_csv_to_file(self, csvfile, namedtuples):
        header_row = [unmunge_colname(colname) for colname in namedtuples[0]._fields]
        writer = csv.writer(csvfile)
        writer.writerow(header_row)
        for row in namedtuples:
            writer.writerow(row)

    def write_csv(self, filename, namedtuples):
        """
        Write the given rows (as a list of named tuples) into
        the given CSV file in the NYCDB data directory.
        """

        path = self.root_dir / filename
        with path.open("w", newline="") as csvfile:
            self._write_csv_to_file(csvfile, namedtuples)

    def write_zip(self, filename, files):
        """
        Write a ZIP file containing CSV files to the NYC
        data directory, given a dictionary mapping
        filenames to lists of named tuples.
        """

        path = self.root_dir / filename
        with zipfile.ZipFile(path, mode="w") as zf:
            for filename in files:
                out = StringIO()
                self._write_csv_to_file(out, files[filename])
                zf.writestr(filename, out.getvalue())

    def build_everything(self) -> None:
        """
        Load all the NYCDB datasets required for Who Owns What,
        and then run all our custom SQL.
        """

        for dataset in dbtool.get_dataset_dependencies(for_api=False):
            self.load_dataset(dataset)

        with self.get_cursor() as cur:
            create_oca_tables(cur, self.oca_config)
            populate_oca_tables(cur, self.oca_config)

        all_sql = "\n".join(
            [sqlpath.read_text() for sqlpath in dbtool.get_sqlfile_paths()]
        )
        with self.get_cursor() as cur:
            cur.execute(all_sql)


def nycdb_ctx(get_cursor):
    """
    Yield a NYCDB context whose data directory is
    a temporary directory.
    """

    with tempfile.TemporaryDirectory() as dirname:
        for glob in dbtool.WOW_YML["extra_nycdb_test_data"]:
            tempdirpath = Path(dirname)
            for filepath in dbtool.ROOT_DIR.glob(glob):
                tempfile_path = tempdirpath / filepath.name
                tempfile_path.write_text(filepath.read_text())

        yield NycdbContext(dirname, get_cursor)
