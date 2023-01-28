import argparse
import logging
from pathlib import Path

import pandas as pd

from classes.games_dataset import GamesDataset
from utils.dataset import process_games
from utils.logging import setup_logger

DIVISION_ALIASES = {
    "open": ["open", "men"],
    "women": ["women"],
    "mixed": ["mixed", "mix"],
}


def main():
    """
    Take data from all the CSV files in the input folder and join them to create a big Game Table with the clean data;
    export some preliminary summary statistics (no rankings are calculated here).

    Prerequisites:
    * Prepare a folder with the tournament result data - CSV files with columns Tournament, Date, Team_1, Team_2,
      Score_1, Score_2, and Division
    * Add to the same folder a TXT file per division specifying the teams in the EUF system; multiple aliases can be
      defined for each team in the same row, separated with commas (filename should be teams-<division>.txt)
    * Add to the same folder a TXT file with the pairs <team>, <tournament>; specifying that the given team has met the
      EUF roster requirements for the particular tournament (filename should be teams_at_tournaments-<division>.txt)

    Arguments:
    * --input - path to the folder with all necessary files
    * --division - women/mixed/open
    * --season - current year
    * --output - path to the folder to save the output CSVs

    Procedure:
    * Read the tournament results CSVs and take only the games for the given division
    * Read the list of EUF teams; replace aliases where applicable
    * Read teams at tournaments list; add suffix to all teams without EUF-sanctioned roster for the given tournament
    * Process the Game Table (check for invalid rows)
    * Calculate basic statistics for the season (without any rankings)
    * Save the output CSVs

    Outputs:
    * CSVs with Games, Tournaments, Calendar, and Summary (without any rankings)
    """
    parser = argparse.ArgumentParser(description="EUF data preparation parser.")
    parser.add_argument("--input", required=True, type=Path, help="Path to the folder with all necessary files")
    parser.add_argument("--division", required=True, choices=["women", "mixed", "open"], help="Division (women/mixed/open)")
    parser.add_argument("--season", required=True, type=int, help="Current year (for naming purposes)")
    parser.add_argument("--output", required=True, type=Path, help="Path to the folder to save the output CSVs")
    args = parser.parse_args()

    setup_logger()
    logger = logging.getLogger("ranking.data_preparation")

    with open(args.input / f"teams-{args.division}.txt", "r") as f:
        teams_euf = f.read().split("\n")
    teams_euf = [t for t in teams_euf if len(t) > 0]  # Remove possible empty rows
    logger.info(f"{len(teams_euf)} teams defined for the {args.division} division.")

    df_list = []
    for filename in [f for f in args.input.iterdir() if f.suffix == ".csv"]:
        df_tournament = pd.read_csv(filename)
        df_tournament = df_tournament.loc[df_tournament["Division"].str.lower().isin(DIVISION_ALIASES[args.division])]
        df_list.append(df_tournament.drop(columns="Division"))
    df_games = pd.concat(df_list)
    logger.info(f"{df_games.shape[0]} raw games found for the {args.division} division.")

    # Change the aliases of the teams to the original team name and remove them from the teams list
    for i, team in enumerate(teams_euf):
        if ", " in team:  # There are aliases defined for the team name
            aliases = team.split(", ")[1:]
            teams_euf[i] = team.split(", ")[0]
            df_games["Team_1"].apply(lambda x: team if x in aliases else x)
            df_games["Team_2"].apply(lambda x: team if x in aliases else x)

    # Add suffix `@ <tournament>` to all teams without valid EUF roster for the given tournament
    with open(args.input / f"teams_at_tournaments-{args.division}.txt", "r") as f:
        teams_at_tournaments = f.read().split("\n")
    teams_at_tournaments = [t.split(", ") for t in teams_at_tournaments if len(t) > 0]
    df_teams_at_tournaments = pd.DataFrame(teams_at_tournaments, columns=["Team", "Tournament"])
    df_teams_at_tournaments = df_teams_at_tournaments.pivot_table(index="Team", columns="Tournament", aggfunc="size", fill_value=0)
    for team_lbl in ["Team_1", "Team_2"]:
        df_games[team_lbl] = df_games.apply(
            lambda x: add_suffix_if_not_euf_team_with_roster(df_teams_at_tournaments, x[team_lbl], x["Tournament"]),
            axis=1,
        )

    df_games = process_games(df_games)
    logger.info(f"{df_games.shape[0]} valid games found for the {args.division} division.")

    dataset = GamesDataset(df_games, f"EUF-{args.season}-{args.division}")
    dataset.games.to_csv(args.output / f"{dataset.name}-games.csv", index=False)
    dataset.tournaments.to_csv(args.output / f"{dataset.name}-tournaments.csv")
    dataset.calendar.to_csv(args.output / f"{dataset.name}-calendar.csv")
    dataset.summary.to_csv(args.output / f"{dataset.name}-summary.csv")
    logger.info(f"CSV files saved to {args.output}.")


def add_suffix_if_not_euf_team_with_roster(df_teams_at_tournaments: pd.DataFrame, team: str, tournament: str) -> str:
    """
    Add suffix @ <tournament> the the non-EUF teams or EUF teams which did not fulfilled roster requirements for the
    given tournament.

    :param df_teams_at_tournaments: DataFrame of 0/1 with teams as indices and tournaments as columns
    :param team: Team name
    :param tournament: Tournament name
    :return: Final team name (either with suffix or not)
    """
    if (
        (team not in df_teams_at_tournaments.index)
        or (tournament not in df_teams_at_tournaments.columns)
        or (not df_teams_at_tournaments.loc[team, tournament])
    ):
        return f"{team} @ {tournament}"
    else:
        return team


if __name__ == "__main__":
    main()


