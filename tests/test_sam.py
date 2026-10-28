from catchlength.sam import parse, rescue_prompt

# real SAM 3.1 output, from meta-models/meta-sam's README
SAMPLE = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
          "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
          ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
          "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>")


def test_parse_real_output_to_full_frame_masks():
    d = parse(SAMPLE, (320, 334))
    assert [x.id for x in d] == ["0", "1"]
    m = d[0].mask
    assert m.shape == (334, 320) and m.any()
    ys, xs = m.nonzero()
    assert 211 <= xs.min() and xs.max() < 271 and 228 <= ys.min() and ys.max() < 255  # inside its box


def test_empty_output_is_zero_matches():
    assert parse("", (320, 334)) == []


def test_rescue_prompt_grammar():
    t = rescue_prompt((1920, 1080), [{"id": 7, "box": (100, 200, 400, 300), "negatives": [(450, 250)]}])
    assert t == "<0f>7<|box;x1=100;y1=200;x2=400;y2=300;w=1920;h=1080|>-<|point;x=450;y=250;w=1920;h=1080|>"
