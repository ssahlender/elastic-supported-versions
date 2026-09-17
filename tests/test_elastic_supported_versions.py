import datetime as dt
import unittest

import elastic_supported_versions as subject


EOL_HTML = """
<html>
  <body>
    <h2>Current versions</h2>
    <table>
      <tr>
        <td>Core Stack</td>
        <td>Elasticsearch Kibana Logstash Elastic Agent and Beats</td>
        <td>9.x</td>
        <td>15-Oct-2027</td>
      </tr>
      <tr>
        <td>Orchestration</td>
        <td>Elastic Cloud Enterprise</td>
        <td>4.x</td>
        <td>15-Oct-2027</td>
      </tr>
      <tr>
        <td>Elastic Cloud on Kubernetes</td>
        <td>3.x</td>
        <td>15-Oct-2027</td>
      </tr>
      <tr><td>APM Agents</td><td>APM Java Agent</td></tr>
    </table>
    <h2>Prior versions</h2>
    <p>Any version prior to the versions shown in the tables below is unsupported.</p>
    <table>
      <tr>
        <td>Core Stack</td>
        <td>Elasticsearch Kibana Logstash Elastic Agent and Beats</td>
        <td>8.x</td>
        <td>15-Jan-2027</td>
        <td>15-Jul-2027</td>
      </tr>
      <tr>
        <td>7.17.x</td>
        <td>15-Apr-2025</td>
        <td>15-Jan-2026</td>
      </tr>
      <tr>
        <td>Orchestration</td>
        <td>Elastic Cloud Enterprise</td>
        <td>3.x</td>
        <td>15-Jan-2027</td>
      </tr>
      <tr>
        <td>Elastic Cloud on Kubernetes</td>
        <td>2.x</td>
        <td>15-Jan-2027</td>
      </tr>
      <tr>
        <td>1.9.x</td>
        <td>15-Apr-2025</td>
      </tr>
      <tr><td>APM Agents</td><td>APM Go Agent</td></tr>
    </table>
    <h2>Retired Software Products</h2>
    <p>Below Software Products are being retired and will have no more Major Releases.</p>
    <table>
      <tr>
        <td>Core Stack</td>
        <td>Elasticsearch</td>
        <td>8.x</td>
        <td>01-Jan-2000</td>
      </tr>
      <tr>
        <td>Orchestration</td>
        <td>Elastic Cloud on Kubernetes</td>
        <td>2.x</td>
        <td>01-Jan-2000</td>
      </tr>
      <tr><td>APM Agents</td><td>APM Ruby Agent</td></tr>
    </table>
  </body>
</html>
"""


class ElasticEolParserTest(unittest.TestCase):
    def test_core_stack_terms_include_current_and_prior_but_not_retired(self) -> None:
        self.assertEqual(
            subject.find_core_stack_terms(EOL_HTML),
            {
                9: dt.date(2027, 10, 15),
                8: dt.date(2027, 1, 15),
                7: dt.date(2025, 4, 15),
            },
        )

    def test_eck_terms_include_current_and_prior_but_not_retired(self) -> None:
        self.assertEqual(
            subject.find_cloud_on_k8s_terms(EOL_HTML),
            {
                3: dt.date(2027, 10, 15),
                2: dt.date(2027, 1, 15),
                1: dt.date(2025, 4, 15),
            },
        )

    def test_active_policy_text_fails_closed_without_retired_boundary(self) -> None:
        with self.assertRaises(ValueError):
            subject.active_policy_text("Core Stack 8.x 15-Jan-2027 Orchestration")


if __name__ == "__main__":
    unittest.main()
