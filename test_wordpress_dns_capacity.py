"""DNS capacity regression test. No external network access."""
import threading
import time
import unittest
from unittest.mock import patch
from wordpress_dns_deadline import getaddrinfo_with_deadline, DNSDeadlineExceeded

class DNSCapacityTests(unittest.TestCase):
    def test_four_blocked_lookups_limit_capacity_and_recover(self):
        gate=threading.Event()
        started=threading.Condition()
        counter=[0]
        def blocked(*args, **kwargs):
            with started:
                counter[0]+=1
                started.notify_all()
            gate.wait(5)
            return [(None,None,None,None,("8.8.8.8",443))]
        try:
            with patch("wordpress_dns_deadline.socket.getaddrinfo",side_effect=blocked):
                for i in range(4):
                    with self.subTest(worker=i),self.assertRaises(DNSDeadlineExceeded):
                        getaddrinfo_with_deadline("example.com",timeout=.04)
                with started:
                    self.assertTrue(started.wait_for(lambda:counter[0]==4,timeout=1))
                with self.assertRaises(DNSDeadlineExceeded):
                    getaddrinfo_with_deadline("example.com",timeout=.04)
                self.assertEqual(counter[0],4,"Fifth resolver must not be launched")
        finally:
            gate.set()
        # Wait for daemon workers to actually return and release capacity.
        from wordpress_dns_deadline import _SLOTS
        for _ in range(100):
            if _SLOTS.acquire(blocking=False):
                _SLOTS.release()
                break
            time.sleep(.01)
        else:
            self.fail("DNS capacity was not recovered")
    def test_late_lookup_result_never_authorizes_call(self):
        gate=threading.Event()
        try:
            with patch("wordpress_dns_deadline.socket.getaddrinfo",side_effect=lambda *a,**k:(gate.wait(5),[("late",)])[1]):
                with self.assertRaises(DNSDeadlineExceeded):
                    getaddrinfo_with_deadline("example.com",timeout=.02)
        finally:
            gate.set()
if __name__=="__main__":
    unittest.main()
