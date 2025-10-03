import os
import pandas as pd
from output_handler import save_responses_to_csv

def test_save_responses_to_csv_creates_file(tmp_path):
    output_path = tmp_path / "output.csv"
    data = [("Prompt 1", "Response 1"), ("Prompt 2", "Response 2")]

    save_responses_to_csv(data, str(output_path))

    assert os.path.exists(output_path)

    # Load CSV and verify contents
    df = pd.read_csv(output_path)
    assert list(df.columns) == ["Prompt", "Response"]
    assert df.iloc[0]["Prompt"] == "Prompt 1"
    assert df.iloc[0]["Response"] == "Response 1"
