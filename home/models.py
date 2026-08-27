from django.db import models


class PokedexBase(models.Model):
    """One row per draftable Pokémon in a season's draft board, combining
    draft_board.json (points), sprites.json (sprite_id), and pokedex.json
    (species data). Only Pokémon present in that season's draft_board.json
    are included -- see home/management/commands/load_s4_pokedex.py for how
    rows are built and how draft-board names get matched to pokedex.json's
    Showdown-ID keys."""

    name = models.CharField(max_length=64, primary_key=True)
    points = models.IntegerField()
    sprite_id = models.CharField(max_length=64)

    pokedex_num = models.IntegerField(null=True)
    types = models.JSONField(default=list)
    base_hp = models.IntegerField(null=True)
    base_atk = models.IntegerField(null=True)
    base_def = models.IntegerField(null=True)
    base_spa = models.IntegerField(null=True)
    base_spd = models.IntegerField(null=True)
    base_spe = models.IntegerField(null=True)
    abilities = models.JSONField(default=dict)
    height_m = models.FloatField(null=True)
    weight_kg = models.FloatField(null=True)
    color = models.CharField(max_length=32, null=True)
    evos = models.JSONField(default=list)
    egg_groups = models.JSONField(default=list)
    tier = models.CharField(max_length=16, null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class S1Pokedex(PokedexBase):
    class Meta:
        db_table = "s1_pokedex"
        verbose_name_plural = "S1 pokedex"


class S2Pokedex(PokedexBase):
    class Meta:
        db_table = "s2_pokedex"
        verbose_name_plural = "S2 pokedex"


class S3Pokedex(PokedexBase):
    class Meta:
        db_table = "s3_pokedex"
        verbose_name_plural = "S3 pokedex"


class S4Pokedex(PokedexBase):
    class Meta:
        db_table = "s4_pokedex"
        verbose_name_plural = "S4 pokedex"


class RostersBase(models.Model):
    """One row per team roster, loaded from rosters.json -- see
    home/management/commands/load_s4_rosters.py."""

    coach_name = models.CharField(max_length=64, primary_key=True)
    team_name = models.CharField(max_length=128, null=True)
    logo = models.CharField(max_length=256, default="")
    pokemon = models.JSONField(default=list, help_text="List of {name, points}.")
    free_agents_used = models.IntegerField(default=0)

    class Meta:
        abstract = True

    def __str__(self):
        return self.team_name or self.coach_name


class S1Rosters(RostersBase):
    class Meta:
        db_table = "s1_rosters"
        verbose_name_plural = "S1 rosters"


class S2Rosters(RostersBase):
    class Meta:
        db_table = "s2_rosters"
        verbose_name_plural = "S2 rosters"


class S3Rosters(RostersBase):
    class Meta:
        db_table = "s3_rosters"
        verbose_name_plural = "S3 rosters"


class S4Rosters(RostersBase):
    class Meta:
        db_table = "s4_rosters"
        verbose_name_plural = "S4 rosters"


class ScheduleBase(models.Model):
    """One row per scheduled match, loaded from schedule.json -- see
    home/management/commands/load_s4_schedule.py. (week, match_index) is
    this season's stable address for a match, mirroring how schedule.json
    itself is indexed by set_match_replay()/set_match_from_replay()."""

    week = models.IntegerField()
    week_label = models.CharField(max_length=32)
    match_index = models.IntegerField(help_text="Position of this match within its week's matches list.")
    player1 = models.CharField(max_length=64)
    player2 = models.CharField(max_length=64)
    replay_url = models.CharField(max_length=512, null=True)
    winner = models.CharField(max_length=8, null=True)
    margin = models.IntegerField(null=True)
    stats = models.JSONField(null=True, help_text="{'player1': [...], 'player2': [...]} per-Pokemon stat dicts.")

    class Meta:
        abstract = True

    def __str__(self):
        return f"Week {self.week}: {self.player1} vs {self.player2}"


class S1Schedule(ScheduleBase):
    class Meta:
        db_table = "s1_schedule"
        verbose_name_plural = "S1 schedule"
        unique_together = ("week", "match_index")
        ordering = ["week", "match_index"]


class S2Schedule(ScheduleBase):
    class Meta:
        db_table = "s2_schedule"
        verbose_name_plural = "S2 schedule"
        unique_together = ("week", "match_index")
        ordering = ["week", "match_index"]


class S3Schedule(ScheduleBase):
    class Meta:
        db_table = "s3_schedule"
        verbose_name_plural = "S3 schedule"
        unique_together = ("week", "match_index")
        ordering = ["week", "match_index"]


class S4Schedule(ScheduleBase):
    class Meta:
        db_table = "s4_schedule"
        verbose_name_plural = "S4 schedule"
        unique_together = ("week", "match_index")
        ordering = ["week", "match_index"]


class FreeAgencyLogBase(models.Model):
    """One row per free agency transaction, loaded from
    free_agency_log.json -- see
    home/management/commands/load_s4_free_agency_log.py."""

    coach = models.CharField(max_length=64)
    team_name = models.CharField(max_length=128, null=True)
    drops = models.JSONField(default=list, help_text="List of {name, points}.")
    pickups = models.JSONField(default=list, help_text="List of {name, points}.")

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.coach}: {len(self.drops)} drop(s), {len(self.pickups)} pickup(s)"


class S1FreeAgencyLog(FreeAgencyLogBase):
    class Meta:
        db_table = "s1_free_agency_log"
        verbose_name_plural = "S1 free agency log"
        ordering = ["id"]


class S2FreeAgencyLog(FreeAgencyLogBase):
    class Meta:
        db_table = "s2_free_agency_log"
        verbose_name_plural = "S2 free agency log"
        ordering = ["id"]


class S3FreeAgencyLog(FreeAgencyLogBase):
    class Meta:
        db_table = "s3_free_agency_log"
        verbose_name_plural = "S3 free agency log"
        ordering = ["id"]


class S4FreeAgencyLog(FreeAgencyLogBase):
    class Meta:
        db_table = "s4_free_agency_log"
        verbose_name_plural = "S4 free agency log"
        ordering = ["id"]
