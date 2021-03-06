import datetime

import pytz
import requests_mock

from exchangelib import EWSDateTime, EWSDate, EWSTimeZone, UTC
from exchangelib.errors import NonExistentTimeError, AmbiguousTimeError, UnknownTimeZone, NaiveDateTimeNotAllowed
from exchangelib.winzone import generate_map, CLDR_TO_MS_TIMEZONE_MAP, CLDR_WINZONE_URL
from exchangelib.util import CONNECTION_ERRORS

from .common import TimedTestCase


class EWSDateTimeTest(TimedTestCase):

    def test_super_methods(self):
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertIsInstance(EWSDateTime.now(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcnow(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789, tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcfromtimestamp(123456789), EWSDateTime)

    def test_ewstimezone(self):
        # Test autogenerated translations
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'Europe/Copenhagen')
        self.assertEqual(tz.ms_id, 'Romance Standard Time')
        # self.assertEqual(EWSTimeZone.timezone('Europe/Copenhagen').ms_name, '')  # EWS works fine without the ms_name

        # Test localzone()
        tz = EWSTimeZone.localzone()
        self.assertIsInstance(tz, EWSTimeZone)

        # Test common helpers
        tz = EWSTimeZone.timezone('UTC')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'UTC')
        self.assertEqual(tz.ms_id, 'UTC')
        tz = EWSTimeZone.timezone('GMT')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.zone, 'GMT')
        self.assertEqual(tz.ms_id, 'UTC')

        # Test mapper contents. Latest map from unicode.org has 394 entries
        self.assertGreater(len(EWSTimeZone.PYTZ_TO_MS_MAP), 300)
        for k, v in EWSTimeZone.PYTZ_TO_MS_MAP.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, tuple)
            self.assertEqual(len(v), 2)
            self.assertIsInstance(v[0], str)

        # Test timezone unknown by pytz
        with self.assertRaises(UnknownTimeZone):
            EWSTimeZone.timezone('UNKNOWN')

        # Test timezone known by pytz but with no Winzone mapping
        tz = pytz.timezone('Africa/Tripoli')
        # This hack smashes the pytz timezone cache. Don't reuse the original timezone name for other tests
        tz.zone = 'UNKNOWN'
        with self.assertRaises(UnknownTimeZone):
            EWSTimeZone.from_pytz(tz)

        # Test __eq__ with non-EWSTimeZone compare
        self.assertFalse(EWSTimeZone.timezone('GMT') == pytz.utc)

        # Test from_ms_id() with non-standard MS ID
        self.assertEqual(EWSTimeZone.timezone('Europe/Copenhagen'), EWSTimeZone.from_ms_id('Europe/Copenhagen'))

    def test_localize(self):
        # Test some cornercases around DST
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0))),
            '2023-10-29 02:36:00+01:00'
        )
        with self.assertRaises(AmbiguousTimeError):
            tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=None)
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=True)),
            '2023-10-29 02:36:00+02:00'
        )
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0))),
            '2023-03-26 02:36:00+01:00'
        )
        with self.assertRaises(NonExistentTimeError):
            tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=None)
        self.assertEqual(
            str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=True)),
            '2023-03-26 02:36:00+02:00'
        )

    def test_ewsdatetime(self):
        # Test a static timezone
        tz = EWSTimeZone.timezone('Etc/GMT-5')
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05+05:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=<StaticTzInfo 'Etc/GMT-5'>)"
        )

        # Test a DST timezone
        tz = EWSTimeZone.timezone('Europe/Copenhagen')
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05+01:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=<DstTzInfo 'Europe/Copenhagen' CET+1:00:00 STD>)"
        )

        # Test from_string
        with self.assertRaises(NaiveDateTimeNotAllowed):
            EWSDateTime.from_string('2000-01-02T03:04:05')
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05+01:00'),
            UTC.localize(EWSDateTime(2000, 1, 2, 2, 4, 5))
        )
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05Z'),
            UTC.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        )
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05+01:00'), EWSDateTime)
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05Z'), EWSDateTime)

        # Test addition, subtraction, summertime etc
        self.assertIsInstance(dt + datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - EWSDateTime.now(tz=tz), datetime.timedelta)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertEqual(dt, EWSDateTime.from_datetime(tz.localize(datetime.datetime(2000, 1, 2, 3, 4, 5))))
        self.assertEqual(dt.ewsformat(), '2000-01-02T03:04:05+01:00')
        utc_tz = EWSTimeZone.timezone('UTC')
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-01-02T02:04:05Z')
        # Test summertime
        dt = tz.localize(EWSDateTime(2000, 8, 2, 3, 4, 5))
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-08-02T01:04:05Z')
        # Test normalize, for completeness
        self.assertEqual(tz.normalize(dt).ewsformat(), '2000-08-02T03:04:05+02:00')
        self.assertEqual(utc_tz.normalize(dt, is_dst=True).ewsformat(), '2000-08-02T01:04:05Z')

        # Test in-place add and subtract
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, tz.localize(EWSDateTime(2000, 1, 3, 3, 4, 5)))
        dt = tz.localize(EWSDateTime(2000, 1, 2, 3, 4, 5))
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, tz.localize(EWSDateTime(2000, 1, 1, 3, 4, 5)))

        # Test ewsformat() failure
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5)
        with self.assertRaises(ValueError):
            dt.ewsformat()
        # Test wrong tzinfo type
        with self.assertRaises(ValueError):
            EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=pytz.utc)
        with self.assertRaises(ValueError):
            EWSDateTime.from_datetime(EWSDateTime(2000, 1, 2, 3, 4, 5))

    def test_generate(self):
        try:
            self.assertDictEqual(generate_map(), CLDR_TO_MS_TIMEZONE_MAP)
        except CONNECTION_ERRORS:
            # generate_map() requires access to unicode.org, which may be unavailable. Don't fail test, since this is
            # out of our control.
            pass

    @requests_mock.mock()
    def test_generate_failure(self, m):
        m.get(CLDR_WINZONE_URL, status_code=500)
        with self.assertRaises(ValueError):
            generate_map()

    def test_ewsdate(self):
        self.assertEqual(EWSDate(2000, 1, 1).ewsformat(), '2000-01-01')
        self.assertEqual(EWSDate.from_string('2000-01-01'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01Z'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01+01:00'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01-01:00'), EWSDate(2000, 1, 1))
        self.assertIsInstance(EWSDate(2000, 1, 2) - EWSDate(2000, 1, 1), datetime.timedelta)
        self.assertIsInstance(EWSDate(2000, 1, 2) + datetime.timedelta(days=1), EWSDate)
        self.assertIsInstance(EWSDate(2000, 1, 2) - datetime.timedelta(days=1), EWSDate)

        # Test in-place add and subtract
        dt = EWSDate(2000, 1, 2)
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 3))
        dt = EWSDate(2000, 1, 2)
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 1))

        with self.assertRaises(ValueError):
            EWSDate.from_date(EWSDate(2000, 1, 2))
