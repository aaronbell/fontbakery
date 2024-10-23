# pylint: disable=line-too-long  # This is data, not code
PROFILE = {
    "include_profiles": ["universal"],
    "pending_review": [
        "opentype/weight_class_fvar",
        "opentype/slant_direction",
        "cjk_not_enough_glyphs",
        "cmap/format_12",
        "color_cpal_brightness",
        "colorfont_tables",
        "empty_glyph_on_gid1_for_colrv0",
        "empty_letters",
        "family/control_chars",
        "file_size",
        "fvar_name_entries",
        "fontdata_namecheck",
        "glyf_nested_components",
        "hinting_impact",
        "inconsistencies_between_fvar_stat",
        "integer_ppem_if_hinted",
        "kerning_for_non_ligated_sequences",
        "ligature_carets",
        "mandatory_avar_table",
        "missing_small_caps_glyphs",
        "name/char_restrictions",
        "name/family_and_style_max_length",
        "no_mac_entries",
        "overlapping_path_segments",
        "render_own_name",
        "smart_dropout",
        "stylisticset_description",
        "typographic_family_name",
        "varfont/consistent_axes",
        "varfont/duplexed_axis_reflow",
        "varfont/instances_in_order",
        "varfont/unsupported_axes",
        "vtt_volt_data",  # very similar to vttclean, may be a good idea to merge them.
        "vttclean",
    ],
    "sections": {
        "Font Bureau Checks": [
            "fontbureau/ytlc_sanity",
        ],
    },
}
