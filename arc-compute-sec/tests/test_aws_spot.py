import json

import responses

from feeds import aws_spot


FAKE_SPOT = {
    "vers": 0.01,
    "config": {
        "rate": "perhr",
        "valueColumns": ["linux"],
        "regions": [
            {
                "region": "us-east-1",
                "instanceTypes": [
                    {
                        "type": "generalCurrentGen",
                        "sizes": [
                            {
                                "size": "p4d.24xlarge",
                                "valueColumns": [
                                    {"name": "linux", "prices": {"USD": "12.40"}}
                                ],
                            },
                            {
                                "size": "p5.48xlarge",
                                "valueColumns": [
                                    {"name": "linux", "prices": {"USD": "32.00"}}
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    },
}


@responses.activate
def test_fetch_gpu_spot_parses_both_instances():
    responses.add(
        responses.GET, aws_spot._SPOT_FEED,
        body=json.dumps(FAKE_SPOT), status=200, content_type="application/json",
    )
    pts = aws_spot.fetch_gpu_spot(regions=("us-east-1",))
    assert len(pts) == 2
    by_inst = {p.instance_type: p for p in pts}
    p4 = by_inst["p4d.24xlarge"]
    p5 = by_inst["p5.48xlarge"]
    assert p4.price_per_hour == 12.40
    assert p4.price_per_gpu_hour == 12.40 / 8
    assert p5.price_per_gpu_hour == 32.00 / 8


@responses.activate
def test_fetch_handles_jsonp_wrapper():
    body = "callback(" + json.dumps(FAKE_SPOT) + ");"
    responses.add(
        responses.GET, aws_spot._SPOT_FEED,
        body=body, status=200, content_type="text/javascript",
    )
    pts = aws_spot.fetch_gpu_spot(regions=("us-east-1",))
    assert pts
