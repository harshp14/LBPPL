from django.test import SimpleTestCase

from home.replay_parser import _parse_log


class ReplayPreviewTests(SimpleTestCase):
    def test_unused_preview_pokemon_are_included(self):
        log = "\n".join([
            "|player|p1|Ash|",
            "|player|p2|Gary|",
            "|clearpoke",
            "|poke|p1|Pikachu",
            "|poke|p1|Charizard",
            "|poke|p2|Bulbasaur",
            "|poke|p2|Squirtle",
            "|teampreview",
            "|switch|p1a: Pika|Pikachu|100/100",
            "|switch|p2a: Bulba|Bulbasaur|100/100",
            "|turn|1",
            "|win|Ash",
        ])
        result = _parse_log(log)

        self.assertEqual([m["pokemon"] for m in result["p1"]], ["Pikachu", "Charizard"])
        self.assertEqual([m["appeared"] for m in result["p1"]], [True, False])
        self.assertEqual([m["team_position"] for m in result["p1"]], [1, 2])
        self.assertEqual(result["p1"][1]["kills"], 0)
        self.assertFalse(result["p1"][1]["died"])

        self.assertEqual([m["pokemon"] for m in result["p2"]], ["Bulbasaur", "Squirtle"])
        self.assertEqual([m["appeared"] for m in result["p2"]], [True, False])

    def test_mega_forme_still_matches_preview_slot(self):
        log = "\n".join([
            "|player|p1|Ash|",
            "|player|p2|Gary|",
            "|clearpoke",
            "|poke|p1|Tyranitar, M",
            "|poke|p1|Sandslash-Alola, F",
            "|poke|p2|Greninja, F",
            "|teampreview",
            "|switch|p1a: Ttar|Tyranitar, M|100/100",
            "|switch|p2a: Gren|Greninja, F|100/100",
            "|detailschange|p1a: Ttar|Tyranitar-Mega, M",
            "|win|Ash",
        ])
        result = _parse_log(log)
        self.assertEqual(
            [(m["pokemon"], m["appeared"], m["team_position"]) for m in result["p1"]],
            [("Tyranitar-Mega", True, 1), ("Sandslash-Alola", False, 2)],
        )
        self.assertEqual(result["p2"][0]["pokemon"], "Greninja")
        self.assertEqual(len(result["p2"]), 1)

    def test_illusion_does_not_duplicate_or_steal_preview_slots(self):
        # Zoroark switches in disguised as Terapagos, then |replace| reveals
        # it; the real Terapagos later switches in under its own name.
        log = "\n".join([
            "|player|p1|Ash|",
            "|player|p2|Gary|",
            "|clearpoke",
            "|poke|p1|Pikachu",
            "|poke|p2|Terapagos, M",
            "|poke|p2|Zoroark-Hisui, M",
            "|poke|p2|Reuniclus, M",
            "|teampreview",
            "|switch|p1a: Pika|Pikachu|100/100",
            "|switch|p2a: Terapagos|Terapagos, M|100/100",
            "|switch|p2a: Reuniclus|Reuniclus, M|100/100",
            "|switch|p2a: Terapagos|Terapagos, M|200/200",
            "|replace|p2a: Zoroark|Zoroark-Hisui, M",
            "|switch|p2a: Terapagos|Terapagos-Terastal, M|100/100",
            "|win|Ash",
        ])
        result = _parse_log(log)
        p2 = [(m["pokemon"], m["appeared"], m["team_position"]) for m in result["p2"]]
        self.assertEqual(len(p2), 3)
        self.assertEqual(
            sorted(p2, key=lambda t: t[2]),
            [
                ("Terapagos-Terastal", True, 1),
                ("Zoroark-Hisui", True, 2),
                ("Reuniclus", True, 3),
            ],
        )
