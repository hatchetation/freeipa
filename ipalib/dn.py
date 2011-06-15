# Authors:
#   John Dennis <jdennis@redhat.com>
#
# Copyright (C) 2011  Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from ldap.dn import str2dn, dn2str
from ldap import DECODING_ERROR
from copy import deepcopy

__all__ = ['AVA', 'RDN', 'DN']

'''

Goal
----

To allow a Python programmer the ability to operate on DN's
(Distinguished Names) in a simple intuitive manner supporting all the
Pythonic mechanisms for manipulating objects such that the simple
majority case remains simple with simple code, yet the corner cases
are fully supported. With the result both simple and complex cases are
100% correct.

This is achieved with a fair of amount of syntax sugar which is best
described as "Do What I Mean" (i.e. DWIM). The class implementations
take simple expressions and internally convert them to their more
complex full definitions hiding much of the complexity from the
programmer.

Anatomy of a DN
---------------

Some definitions:

AVA
    An AVA is an Attribute Value Assertion. In more simple terms it's
    an attribute value pair typically expressed as attr=value
    (e.g. cn=Bob). Both the attr and value in an AVA when expressed in
    a string representation are subject to encoding rules.

RDN
    A RDN is a Relative Distinguished Name. A RDN is a non-empty set of
    AVA's. In the common case a RDN is single valued consisting of 1
    AVA (e.g. cn=Bob). But a RDN may be multi-valued consisting of
    more than one AVA. Because the RDN is a set of AVA's the AVA's are
    unordered when they appear in a multi-valued RDN. In the string
    representation of a RDN AVA's are separated by the plus sign (+).

DN
    A DN is a ordered sequence of 1 or more RDN's. In the string
    representation of a DN each RDN is separated by a comma (,)

Thus a DN is:

Sequence of set of <encoded attr, encoded value> pairs

The following are valid DN's

# 1 RDN with 1 AVA (e.g. cn=Bob)
RDN(AVA)

# 2 RDN's each with 1 AVA (e.g. cn=Bob,dc=redhat.com)
RDN(AVA),RDN(AVA)

# 2 RDN's the first RDN is multi-valued with 2 AVA's
# the second RDN is singled valued with 1 AVA
# (e.g. cn=Bob+ou=people,dc=redhat.com
RDN({AVA,AVA}),RDN(AVA)

Common programming mistakes
---------------------------

DN's present a pernicious problem for programmers. They appear to have
a very simple string format in the majority case, a sequence of
attr=value pairs separated by commas. For example:

dn='cn=Bob,ou=people,dc=redhat,dc=com'

As such there is a tendency to believe you can form DN's by simple
string manipulations such as:

dn='%s=%s' % ('cn','Bob') + ',ou=people,dc=redhat,dc=com'

Or to extract a attr & value by searching the string, for example:

attr=dn[0 : dn.find('=')]
value=dn[dn.find('=')+1 : dn.find(',')]

Or compare a value returned by an LDAP query to a known value:

if value == 'Bob'

All of these simple coding assumptions are WRONG and will FAIL when
a DN is not one of the simple DN's which are probably the 95% of all
DN's. This is what makes DN handling pernicious. What works in 95% of
the cases and is simple, fails for the 5% of DN's which are not
simple.

Examples of where the simple assumptions fail are:

* A RDN may be multi-valued

* A multi-valued RDN has no ordering on it's components

* Attr's and values must be UTF-8 encoded

* String representations of AVA's, RDN's and DN's must be completely UTF-8

* An attr or value may have reserved characters which must be escaped.

* Whitespace needs special handling

To complicate matters a bit more the RFC for the string representation
of DN's (RFC 4514) permits a variety of different syntax's each of
which can evaluate to exactly the same DN but have different string
representations. For example, the attr "R,W" which contains a reserved
character (the comma) can be encoded as a string in these different
ways:

'R\,W'          # backslash escape
'R\2cW'         # hexadecimal ascii escape
'#522C57'       # binary encoded

It should be clear a DN string may NOT be a simple string, rather a DN
string is ENCODED. For simple strings the encoding of the DN is
identical to the simple string value (this common case leads to
erroneous assumptions and bugs because it does not account for
encodings).

The openldap library we use at the client level uses the backslash
escape form. The LDAP server we use uses the hexadecimal ascii escape
form. Thus 'R,W' appears as 'R\,W' when sent from the client to the
LDAP server as part of a DN. But when it's returned as a DN from the
server in an LDAP search it's returned as 'R\2cW'. Any attempt to
compare 'R\,W' to 'R\2cW' for equality will fail despite the fact they
are indeed equal once decoded. Such a test fails because you're
comparing two different encodings of the same value. In MIME you
wouldn't expect the base64 encoding of a string to be equal to the
same string encoded as quoted-printable would you?

When you are comparing attrs or values which are part of a DN and
other string you MUST:

* Know if either of the strings have been encoded and make sure you're
  comparing only decoded components component-wise.

* Extract the component from the DN and decode it. You CANNOT decode
  the entire DN as a string and operate on it. Why? Consider a value
  with a comma embedded in it. For example:

  cn=R\2cW,cn=privilege

  Is a DN with 2 RDN components: cn=R,W followed by "cn=privilege"

  But if you decode the entire DN string as a whole you would get:

  cn=R,W,cn=privilege

  Which is a malformed DN with 3 RDN's, the 2nd RDN is invalid.

* Determine if a RDN is multi-valued, if so you must account
  for the fact each AVA component in the multi-valued RDN can appear
  in any order and still be equivalent. For example the following two
  RDN's are equal:

  cn=Bob+ou=people
  ou=people+cn=Bob

  In addition each AVA (cn=Bob & ou=people) needs to be
  INDEPENDENTLY decoded prior to comparing the unordered set of AVA's
  in the multi-valued RDN.

If you are trying to form a new DN or RDN from a raw string you cannot
simply do string concatenation or string formatting unless you ESCAPE
the components independently prior to concatenation, for example:

  base = 'dc=redhat,dc=com'
  value = 'R,W'
  dn = 'cn=%s,%s' % (value, base)

Will result in the malformed DN 'cn=R,W,dc=redhat,dc=com'

Syntax Sugar
------------

The majority of DN's have a simple string form:

attr=value,attr=value

We want the programmer to be able to create DN's, compare them, and
operate on their components as simply and concisely as possible so
the classes are implemented to provide a lot of syntax sugar.

The classes automatically handle UTF-8 <-> Unicode conversions. Every
attr and value which is returned from a class will be Unicode. Every
attr and value assigned into an object will be promoted to
Unicode. All string representations in RFC 4514 format will be UTF-8
and properly escaped. Thus at the "user" or "API" level every string
is Unicode with the single exception that the str() method returns RFC
compliant escaped UTF-8.

RDN's are assumed to be single-valued. If you need a multi-valued RDN
(an exception) you must explicitly create a multi-valued RDN.

Thus DN's are assumed to be a sequence of attr, value pairs.

The attr and value in the pair MUST be strings (we'll see why in a
moment).

You can express any part of a DN as an even numbered sequence of
strings.

   DN('cn', 'Bob', 'dc', 'redhat.com')

This is equivalent to the DN string:

    cn=Bob,dc=redhat.com

And is exactly equal to:

    DN(RDN(AVA('cn','Bob')),RDN(AVA('dc','redhat.com')))

The following are alternative syntax's which are all exactly
equivalent to the above example.

If you prefer to be more explicit about the pair-wise grouping (or you
have to have a pair) you can use tuples or lists with 2 elements.

   DN(('cn', 'Bob'), ('dc', 'redhat.com'))
   DN(['cn', 'Bob'], ['dc', 'redhat.com'])

You can provide a properly escaped string representation.

   DN('cn=Bob,dc=redhat.com')

You can mix and match any of the forms.

   DN('cn', 'Bob', ['dc', 'redhat.com'])
   DN('cn', 'Bob', 'dc=redhat.com')
   DN('cn', 'Bob', RDN('dc', 'redhat.com'))

Note: this is why attr's and values must be strings, the parsing logic
assumes 2 consecutive strings in a sequence is always a single valued
RDN, everything else is interpreted according to it's type.

AVA's have an attr and value property, thus if you have an AVA

# Get the attr and value
ava.attr  -> u'cn'
ava.value -> u'Bob'

# Set the attr and value
ava.attr  = 'cn'
ava.value = 'Bob'

But since RDN's are assumed to be single valued, exactly the same
behavior applies to an RDN (it will throw an exception if the RDN is
not single valued)

# Get the attr and value
rdn.attr  -> u'cn'
rdn.value -> u'Bob'

# Set the attr and value
rdn.attr  = 'cn'
rdn.value = 'Bob'

Also RDN's can be indexed by name or position (see the RDN class doc
for details).

rdn['cn'] -> u'Bob'
rdn[0] -> AVA('cn', 'Bob')

A DN is a sequence of RDN's, as such any of Python's container
operators can be applied to a DN in a intuitive way.

# How many RDN's in a DN?
len(dn)

# WARNING, this a count of RDN's not how characters there are in the
# string representation the dn, instead that would be:
len(str(dn))

# Iterate over each RDN in a DN
for rdn in dn:

# Get the first RDN in a DN
dn[0] -> RDN('cn', 'Bob')

# Get the value of the first RDN in a DN
dn[0].value -> u'Bob'

# Get the value of the first RDN by indexing by attr name
dn['cn'] -> u'Bob'

# WARNING, when a string is used as an index key the FIRST RDN's value
# in the sequence whose attr matches the key is returned. Thus if you
# have a DN like this "cn=foo,cn=bar" then dn['cn'] will always return
# 'foo' even though there is another attr with the name 'cn'. This is
# almost always what the programmer wants. See the class doc for how
# you can override this default behavior and get a list of every value
# whose attr matches the key.

# Set the first RDN in the DN (all are equivalent)
dn[0] = 'cn', 'Bob'
dn[0] = ('cn', 'Bob')
dn[0] = RDN('cn', 'Bob')

dn[0].attr = 'cn'
dn[0].value = 'Bob'

# Get the first two RDN's using slices
dn[0:2]

# Get the last two RDN's using slices
dn[-2:]

# Get a list of all RDN's using slices
dn[:]

# Set the 2nd and 3rd RDN using slices (all are equivalent)
dn[1:4] = 'cn', 'Bob, 'dc', 'redhat.com'
dn[1:4] = ('cn', 'Bob), ('dc', 'redhat.com')
dn[1:4] = RDN('cn', 'Bob), RDN('dc', 'redhat.com')

String representations and escapes:

# To get an RFC compliant string representation of a DN, RDN or AVA
# simply call str() on it or evaluate it in a string context.
str(dn) -> 'cn=Bob,dc=redhat.com'

# When working with attr's and values you do not have to worry about
# escapes, simply use the raw unescaped string in a natural fashion.

rdn = RDN('cn', 'R,W')

# Thus:
rdn.value == 'R,W' -> True

# But:
str(rdn) == 'cn=R,W' -> False
# Because:
str(rdn) -> 'cn=R\2cW' or 'cn='R\,W' # depending on the underlying LDAP library

Equality and Comparing:

# All DN's, RDN's and AVA's support equality testing in an intuitive
# manner.
dn1 = DN('cn', 'Bob')
dn2 = DN(RDN('cn', 'Bob'))
dn1 == dn2 -> True
dn1[0] == dn2[0] -> True
dn1[0].value = 'Bobby'
dn1 == dn2 -> False

# See the class doc for how DN's, RDN's and AVA's compare
# (e.g. cmp()). The general rule is for objects supporting multiple
# values first their lengths are compared, then if the lengths match
# the respective components of each are pair-wise compared until one
# is discovered to be  non-equal

Concatenation and In-Place Addition:

# DN's and RDN's can be concatenated.
# Return a new DN by appending the RDN's of dn2 to dn1
dn3 = dn1 + dn2

# Append a RDN to DN's RDN sequence (all are equivalent)
dn += 'cn', 'Bob'
dn += ('cn', 'Bob')
dn += RDN('cn', 'Bob')

# Append a DN to an existing DN
dn1 += dn2

Finally see the unittest for a more complete set of ways you can
manipulate these objects.

'''

class AVA(object):
    '''
    An AVA is an LDAP Attribute Value Assertion. It is convenient to think of
    AVA's as a <attr,value> pair. AVA's are members of RDN's (Relative
    Distinguished Name).

    The AVA constructor may be invoked with any of the following methods:

    1) With 2 string (or unicode) arguments, the first argument will be the
    attr, the 2nd the value.

    2) With a sigle list or tuple argument containing exactly 2 string (or unicode
    members), the first member is the attr and the second is the value.

    3) With a single string (or unicode) argument, in this case the string will
    be interpretted using the DN syntax described in RFC 4514 to yield a AVA
    <attr,value> pair. The parsing recognizes the DN syntax escaping rules.

    For example:

    ava = AVA('cn', 'Bob')	# case 1: two strings
    ava = AVA(('cn', 'Bob'))    # case 2: 2-valued tuple
    ava = AVA(['cn', 'Bob'])    # case 2: 2-valued list
    ava = AVA('cn=Bob')         # case 3: DN syntax

    AVA object have two properties for accessing their data:

    attr:  the attribute name, cn in our exmaple
    value: the attribute's value, Bob in our example

    When attr and value are returned they will always be unicode. When
    attr or value are set they will be promoted to unicode.

    AVA objects support indexing by name, e.g.

    ava['cn']

    returns the value (Bob in our example). If the index does key does not match
    the attr then a KeyError will be raised.

    AVA objects support equality testing and comparsion (e.g. cmp()). When they
    are compared the attr is compared first, if the 2 attr's are equal then the
    values are compared.

    The str method of an AVA returns the string representation in RFC 4514 DN
    syntax with proper escaping.
    '''
    flags = 0

    def __init__(self, *args):
        if len(args) == 1:
            arg = args[0]
            if isinstance(arg, basestring):
                try:
                    rdns = str2dn(arg.encode('utf-8'))
                except DECODING_ERROR:
                    raise ValueError("malformed AVA string = \"%s\"" % arg)
                if len(rdns) != 1:
                    raise ValueError("multiple RDN's specified by \"%s\"" % (arg))
                rdn = rdns[0]
                if len(rdn) != 1:
                    raise ValueError("multiple AVA's specified by \"%s\"" % (arg))
                ava = rdn[0]
            elif isinstance(arg, (tuple, list)):
                ava = arg
                if len(ava) != 2:
                    raise ValueError("tuple or list must be 2-valued, not \"%s\"" % (ava))
            else:
                raise TypeError("with 1 argument, argument must be str,unicode,tuple or list, got %s instead" % \
                                arg.__class__.__name__)

            attr  = ava[0]
            value = ava[1]
        elif len(args) == 2:
            attr  = args[0]
            value = args[1]
        else:
            raise TypeError("takes 1 or 2 arguments (%d given)" % (len(args)))

        if not isinstance(attr, basestring):
            raise TypeError("attr must be basestring, got %s instead" % attr.__class__.__name__)
        if not isinstance(value, basestring):
            raise TypeError("value must be basestring, got %s instead" % value.__class__.__name__)

        self.attr  = attr.decode('utf-8')
        self.value = value.decode('utf-8')


    def _to_openldap(self):
        return [[(self.attr.encode('utf-8'), self.value.encode('utf-8'), self.flags)]]

    def __str__(self):
        return dn2str(self._to_openldap())

    def __getitem__(self, key):
        if isinstance(key, basestring):
            if key == self.attr:
                return self.value
            raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
        else:
            raise TypeError("unsupported type for %s indexing, must be basestring; not %s" % \
                                (self.__class__.__name__, key.__class__.__name__))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        return self.attr == other.attr and self.value == other.value

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        result = cmp(self.attr, other.attr)
        if result != 0: return result
        result = cmp(self.value, other.value)
        return result

class RDN(object):
    '''
    An RDN is a LDAP Relative Distinguished Name. RDN's are members of DN's
    (Distinguished Name). An RDN contains 1 or more AVA's. If the RDN contains
    more than one AVA it is said to be a multi-valued RDN. When an RDN is
    multi-valued the AVA's are unorderd comprising a set. However this
    implementation orders the AVA's according to the AVA comparison function to
    make equality and comparison testing easier. Think of this a canonical
    normalization (however LDAP does not impose any ordering on multiple AVA's
    within an RDN). Single valued RDN's are the norm.

    The RDN constructor may be invoked in a variety of different ways.

    * When two adjacent string (or unicode) argument appear together in the
    argument list they are taken to be the <attr,value> pair of an AVA. An AVA
    object is constructed and inserted into the RDN. Multiple pairs of strings
    arguments may appear in the argument list, each pair add one additional AVA
    to the RDN.

    * A 2-valued tuple or list denotes the <attr,value> pair of an AVA. The
    first member is the attr and the second member is the value, both members
    must be strings (or unicode). The tuple or list is passed to the AVA
    constructor and the resulting AVA is added to the RDN. Multiple tuples or
    lists may appear in the argument list, each adds one additional AVA to the
    RDN.

    * A single string (or unicode) argument, in this case the string will
    be interpretted using the DN syntax described in RFC 4514 to yield one or
    more AVA <attr,value> pairs. The parsing recognizes the DN syntax escaping
    rules.

    Note, a DN syntax argument is distguished from AVA string pairs by testing
    to see if two strings appear adjacent in the argument list, if so those two
    strings are interpretted as an <attr,value> AVA pair and consumed.

    * A AVA object. Each AVA object in the argument list will be added to the RDN.

    Single AVA Examples:

    RDN('cn', 'Bob')                    # 2 adjacent strings yield 1 AVA
    RDN(('cn', 'Bob'))                  # tuple yields 1 AVA
    RDN('cn=Bob')                       # DN syntax with 1 AVA
    RDN(AVA('cn', 'Bob'))               # AVA object adds 1 AVA

    Multiple AVA Examples:

    RDN('cn', 'Bob', 'ou', 'people')	# 2 strings pairs yield 2 AVA's
    RDN(('cn', 'Bob'),('ou', 'people')) # 2 tuples yields 2 AVA's
    RDN('cn=Bob+ou=people')             # DN syntax with 2 AVA's
    RDN(AVA('cn', 'Bob'),AVA('ou', 'people')) # 2 AVA objects adds 2 AVA's
    RDN('cn', 'Bob', "ou=people')       # 3 strings, 1st two strings form 1 AVA
                                        # 3rd string DN syntax for 1 AVA,
                                        # adds 2 AVA's in total

    Note: The RHS of a slice assignment is interpreted exactly in the
    same manner as the constructor argument list (see above examples).

    RDN objects support iteration over their AVA members. You can iterate all
    AVA members via any Python iteration syntax. RDN objects support full Python
    indexing using bracket [] notation. Examples:

    len(rdn)            # return the number of AVA's
    rdn[0]              # indexing the first AVA
    rdn['cn']           # index by AVA attr, returns AVA value
    for ava in rdn:     # iterate over each AVA
    rdn[:]              # a slice, in this case a copy of each AVA

    WARNING: When indexing by attr (e.g. rdn['cn']) there is a possibility more
    than one AVA has the same attr name as the index key. The default behavior
    is to return the value of the first AVA whose attr matches the index
    key. This behavior can be modified by setting the first_key_match property
    to false in the RDN object. If first_key_match is False a list of all values
    will be returned instead. The first_key_match behavior is the default and is
    useful because duplicate attr names in multi-valued RDN's are rare. We seek
    the most useful common case for programmer friendliness, but you should be
    aware of the caveat.

    RDN objects support the AVA attr and value properties as another programmer
    convenience because the vast majority of RDN's are single valued. The attr
    and value properties return the attr and value properties of the first AVA
    in the RDN, for example:

    rdn = RDN('cn', 'Bob') # rdn has 1 AVA whose attr == 'cn' and value == 'Bob'
    len(rdn) -> 1
    rdn.attr -> u'cn'      # exactly equivalent to rdn[0].attr
    rdn.value -> u'Bob'    # exactly equivalent to rdn[0].value

    When attr and value are returned they will always be unicode. When
    attr or value are set they will be promoted to unicode.

    If an RDN is multi-valued the attr and value properties still return only
    the first AVA's properties, programmer beware! Recall the AVA's in the RDN
    are sorted according the to AVA collating semantics.

    RDN objects support equality testing and comparision. See AVA for the
    definition of the comparision method.

    RDN objects support concatenation and addition with other RDN's or AVA's

    rdn1 + rdn2 # yields a new RDN object with the contents of each RDN.
    rdn1 + ava1 # yields a new RDN object with the contents of rdn1 and ava1

    RDN objects can add AVA's objects via in-place addition.

    rdn1 += rdn2 # rdn1 now contains the sum of rdn1 and rdn2
    rdn1 += ava1 # rdn1 has ava1 added to it.

    The str method of an RDN returns the string representation in RFC 4514 DN
    syntax with proper escaping.
    '''

    flags = 0

    def __init__(self, *args):
        self.first_key_match = True
        self.avas = self._avas_from_sequence(args)
        self.avas.sort()

    def _ava_from_value(self, value):
        if isinstance(value, AVA):
            return value
        elif isinstance(value, basestring):
            try:
                rdns = str2dn(value.encode('utf-8'))
                if len(rdns) != 1:
                    raise ValueError("multiple RDN's specified by \"%s\"" % (value))
                rdn = rdns[0]
                if len(rdn) == 1:
                    return AVA(rdn[0][0], rdn[0][1])
                else:
                    avas = []
                    for ava_tuple in rdn:
                        avas.append(AVA(ava_tuple[0], ava_tuple[1]))
                    return avas
            except DECODING_ERROR:
                raise ValueError("malformed RDN string = \"%s\"" % value)
        elif isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise ValueError("tuple or list must be 2-valued, not \"%s\"" % (value))
            return AVA(value)
        else:
            raise TypeError("must be str,unicode,tuple, or AVA, got %s instead" % \
                            value.__class__.__name__)


    def _avas_from_sequence(self, seq):
        avas = []

        i = 0
        while i < len(seq):
            if i+1 < len(seq)                   and \
               isinstance(seq[i],   basestring) and \
               isinstance(seq[i+1], basestring):
                ava = AVA(seq[i], seq[i+1])
                avas.append(ava)
                i += 2
            else:
                arg = seq[i]
                ava = self._ava_from_value(arg)
                if isinstance(ava, list):
                    avas.extend(ava)
                else:
                    avas.append(ava)
                i += 1
        return avas

    def _to_openldap(self):
        return [[(ava.attr.encode('utf-8'), ava.value.encode('utf-8'), self.flags) for ava in self.avas]]

    def __str__(self):
        return dn2str(self._to_openldap())

    def _next(self):
        for ava in self.avas:
            yield ava

    def __iter__(self):
        return self._next()

    def __len__(self):
        return len(self.avas)

    def __getitem__(self, key):
        if isinstance(key, (int, long, slice)):
            return self.avas[key]
        elif isinstance(key, basestring):
            if self.first_key_match:
                for ava in self.avas:
                    if key == ava.attr:
                        return ava.value
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
            else:
                avas = []
                for ava in self.avas:
                    if key == ava.attr:
                        avas.append(ava.value)
                if len(avas) > 0:
                    return avas
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
        else:
            raise TypeError("unsupported type for %s indexing, must be int, basestring or slice; not %s" % \
                                (self.__class__.__name__, key.__class__.__name__))

    def __setitem__(self, key, value):
        if isinstance(key, (int, long)):
            new_ava = self._ava_from_value(value)
            if isinstance(new_ava, list):
                raise TypeError("multiple AVA's")
            self.avas[key] = new_ava
        elif isinstance(key, slice):
            avas = self._avas_from_sequence(value)
            self.avas[key] = avas
        elif isinstance(key, basestring):
            new_ava = self._ava_from_value(value)
            if isinstance(new_ava, list):
                raise TypeError("cannot assign multiple values to single entry")
            found = False
            i = 0
            while i < len(self.avas):
                if key == self.avas[i].attr:
                    found = True
                    self.avas[i] = new_ava
                    if self.first_key_match: break
                i += 1
            if not found:
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
        else:
            raise TypeError("unsupported type for %s indexing, must be int, basestring or slice; not %s" % \
                                (self.__class__.__name__, key.__class__.__name__))

    def _get_attr(self):
        if len(self.avas) == 0:
            raise IndexError("No AVA's in this RDN")
        return self.avas[0].attr

    def _set_attr(self, new_attr):
        if len(self.avas) == 0:
            raise IndexError("No AVA's in this RDN")

        if not isinstance(new_attr, basestring):
            raise TypeError("attr must be basestring, got %s instead" % new_attr.__class__.__name__)

        self.avas[0].attr = new_attr

    attr  = property(_get_attr, _set_attr)

    def _get_value(self):
        if len(self.avas) == 0:
            raise IndexError("No AVA's in this RDN")
        return self.avas[0].value

    def _set_value(self, new_value):
        if len(self.avas) == 0:
            raise IndexError("No AVA's in this RDN")

        if not isinstance(new_value, basestring):
            raise TypeError("value must be basestring, got %s instead" % new_value.__class__.__name__)

        self.avas[0].value = new_value

    value = property(_get_value, _set_value)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        return self.avas == other.avas

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        result = cmp(len(self), len(other))
        if result != 0: return result
        i = 0
        while i < len(self):
            result = cmp(self[i], other[i])
            if result != 0: return result
            i += 1
        return 0

    def __add__(self, other):
        result = deepcopy(self)
        if isinstance(other, self.__class__):
            for ava in other.avas:
                result.avas.append(deepcopy(ava))
        elif isinstance(other, AVA):
                result.avas.append(deepcopy(other))
        elif isinstance(other, basestring):
            rdn = RDN(other)
            for ava in rdn.avas:
                result.avas.append(deepcopy(ava))
        else:
            raise TypeError("expected RDN, AVA or basestring but got %s" % (other.__class__.__name__))

        result.avas.sort()
        return result

    def __iadd__(self, other):
        if isinstance(other, self.__class__):
            for ava in other.avas:
                self.avas.append(deepcopy(ava))
        elif isinstance(other, AVA):
                self.avas.append(deepcopy(other))
        elif isinstance(other, basestring):
            rdn = RDN(other)
            for ava in rdn.avas:
                self.avas.append(deepcopy(ava))
        else:
            raise TypeError("expected RDN, AVA or basestring but got %s" % (other.__class__.__name__))

        self.avas.sort()
        return self

class DN(object):
    '''
    A DN is a LDAP Distinguished Name. A DN is an ordered sequence of RDN's.

    The DN constructor may be invoked in a variety of different ways.

    * When two adjacent string (or unicode) argument appear together in the
    argument list they are taken to be the <attr,value> pair of a
    singled valued RDN. An RDN
    object is constructed and inserted into the DN. Multiple pairs of strings
    arguments may appear in the argument list, each pair adds one additional RDN
    to the DN.

    * A 2-valued tuple or list denotes the <attr,value> pair of an RDN. The
    first member is the attr and the second member is the value, both members
    must be strings (or unicode). The tuple or list is passed to the RDN
    constructor and the resulting RDN is added to the DN. Multiple tuples or
    lists may appear in the argument list, each adds one additional RDN to the
    DN.

    * A single string (or unicode) argument, in this case the string will
    be interpretted using the DN syntax described in RFC 4514 to yield one or
    more RDN's. The parsing recognizes the DN syntax escaping
    rules.

    Note, a DN syntax argument is distguished from RDN string pairs by testing
    to see if two strings appear adjacent in the argument list, if so those two
    strings are interpretted as an <attr,value> RDN pair and consumed.

    * A RDN object. Each RDN object in the argument list will be added to the DN.

    * A DN object. Each DN object in the argument list will add it's RDN's to the DN.

    Single DN Examples:

    DN('cn', 'Bob')                     # 2 adjacent strings yield 1 RDN
    DN(('cn', 'Bob'))                   # tuple yields 1 RDN
    DN('cn=Bob')                        # DN syntax with 1 RDN
    DN(RDN('cn', 'Bob'))                # RDN object adds 1 RDN

    Multiple RDN Examples:

    DN('cn', 'Bob', 'ou', 'people')	# 2 strings pairs yield 2 RDN's
    DN(('cn', 'Bob'),('ou', 'people'))  # 2 tuples yields 2 RDN's
    DN('cn=Bob,ou=people')              # DN syntax with 2 RDN's
    DN(RDN('cn', 'Bob'),RDN('ou', 'people')) # 2 RDN objects adds 2 RDN's
    DN('cn', 'Bob', "ou=people')        # 3 strings, 1st two strings form 1 RDN
                                        # 3rd string DN syntax for 1 RDN,
                                        # adds 2 RDN's in total
    DN('cn', 'Bob', DN(container), DN(base)) # 1st two strings form 1 RDN
                                        # then the RDN's from container are added
                                        # followed by the RDN from base

    Note: The RHS of a slice assignment is interpreted exactly in the
    same manner as the constructor argument list (see above examples).

    DN objects support iteration over their RDN members. You can iterate all
    RDN members via any Python iteration syntax. DN objects support full Python
    indexing using bracket [] notation. Examples:

    len(rdn)            # return the number of RDN's
    rdn[0]              # indexing the first RDN
    rdn['cn']           # index by RDN attr, returns RDN value
    for ava in rdn:     # iterate over each RDN
    rdn[:]              # a slice, in this case a copy of each RDN

    WARNING: When indexing by attr (e.g. rdn['cn']) there is a possibility more
    than one RDN has the same attr name as the index key. The default behavior
    is to return the value of the first RDN whose attr matches the index
    key. This behavior can be modified by setting the first_key_match property
    to false in the RDN object. If first_key_match is False a list of all values
    will be returned instead. The first_key_match behavior is the default and is
    useful because typical usage is to seek the first matching RDN. We seek
    the most useful common case for programmer friendliness, but you should be
    aware of the caveat.

    DN object support slices.

    # Get the first two RDN's using slices
    dn[0:2]

    # Get the last two RDN's using slices
    dn[-2:]

    # Get a list of all RDN's using slices
    dn[:]

    # Set the 2nd and 3rd RDN using slices (all are equivalent)
    dn[1:4] = 'cn', 'Bob, 'dc', 'redhat.com'
    dn[1:4] = ('cn', 'Bob), ('dc', 'redhat.com')
    dn[1:4] = RDN('cn', 'Bob), RDN('dc', 'redhat.com')

    DN objects support equality testing and comparision. See RDN for the
    definition of the comparision method.

    DN objects support concatenation and addition with other DN's or RDN's
    or strings (interpreted as RFC 4514 DN syntax).

    # yields a new DN object with the RDN's of dn2 appended to the RDN's of dn1
    dn1 + dn2

    # yields a new DN object with the rdn1 appended to the RDN's of dn1
    dn1 + rdn1

    DN objects can add RDN's objects via in-place addition.

    dn1 += dn2  # dn2 RDN's are appended to the dn1's RDN's
    dn1 += rdn1 # dn1 has rdn appended to its RDN's
    dn1 += "dc=redhat.com" # string is converted to DN, then appended

    The str method of an DN returns the string representation in RFC 4514 DN
    syntax with proper escaping.
    '''

    flags = 0

    def __init__(self, *args):
        self.first_key_match = True
        self.rdns = self._rdns_from_sequence(args)

    def _rdn_from_value(self, value):
        if isinstance(value, RDN):
            return value
        elif isinstance(value, basestring):
            try:
                rdns = str2dn(value.encode('utf-8'))
                for rdn_list in rdns:
                    avas = []
                    for ava_tuple in rdn_list:
                        avas.append(AVA(ava_tuple[0], ava_tuple[1]))
                    rdn = RDN(*avas)
                    return rdn
            except DECODING_ERROR:
                raise ValueError("malformed RDN string = \"%s\"" % value)
        elif isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise ValueError("tuple or list must be 2-valued, not \"%s\"" % (rdn))
            rdn = RDN(value)
            return rdn
        else:
            raise TypeError("single argument must be str,unicode,tuple, or RDN, got %s instead" % \
                            value.__class__.__name__)

    def _rdns_from_sequence(self, seq):
        self.first_key_match = True
        rdns = []

        i = 0
        while i < len(seq):
            if i+1 < len(seq)                       and \
               isinstance(seq[i],   basestring) and \
               isinstance(seq[i+1], basestring):
                rdn = RDN(seq[i], seq[i+1])
                rdns.append(rdn)
                i += 2
            else:
                arg = seq[i]
                i += 1
                if isinstance(arg, RDN):
                    rdns.append(arg)
                elif isinstance(arg, DN):
                    for rdn in arg.rdns:
                        rdns.append(deepcopy(rdn))
                elif isinstance(arg, basestring):
                    try:
                        dn_list = str2dn(arg.encode('utf-8'))
                        for rdn_list in dn_list:
                            avas = []
                            for ava_tuple in rdn_list:
                                avas.append(AVA(ava_tuple[0], ava_tuple[1]))
                            rdn = RDN(*avas)
                            rdns.append(rdn)
                    except DECODING_ERROR:
                        raise ValueError("malformed RDN string = \"%s\"" % arg)
                elif isinstance(arg, (tuple, list)):
                    if len(arg) != 2:
                        raise ValueError("tuple or list must be 2-valued, not \"%s\"" % (rdn))
                    rdn = RDN(arg)
                    rdns.append(rdn)
                else:
                    raise TypeError("single argument must be str,unicode,tuple, or RDN, got %s instead" % \
                                    arg.__class__.__name__)
        return rdns

    def _to_openldap(self):
        return [[(ava.attr.encode('utf-8'), ava.value.encode('utf-8'), self.flags) for ava in rdn] for rdn in self.rdns]

    def __str__(self):
        return dn2str(self._to_openldap())

    def _next(self):
        for rdn in self.rdns:
            yield rdn

    def __iter__(self):
        return self._next()

    def __len__(self):
        return len(self.rdns)

    def __getitem__(self, key):
        if isinstance(key, (int, long, slice)):
            return self.rdns[key]
        elif isinstance(key, basestring):
            if self.first_key_match:
                for rdn in self.rdns:
                    if key == rdn.attr:
                        return rdn.value
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
            else:
                rdns = []
                for rdn in self.rdns:
                    if key == rdn.attr:
                        rdns.append(rdn.value)
                if len(rdns) > 0:
                    return rdns
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
        else:
            raise TypeError("unsupported type for %s indexing, must be int, basestring or slice; not %s" % \
                                (self.__class__.__name__, key.__class__.__name__))

    def __setitem__(self, key, value):
        if isinstance(key, (int, long)):
            new_rdn = self._rdn_from_value(value)
            if isinstance(new_rdn, list):
                raise TypeError("multiple RDN's")
            self.rdns[key] = new_rdn
        elif isinstance(key, slice):
            rdns = self._rdns_from_sequence(value)
            self.rdns[key] = rdns
        elif isinstance(key, basestring):
            new_rdn = self._rdn_from_value(value)
            if isinstance(new_rdn, list):
                raise TypeError("cannot assign multiple values to single entry")
            found = False
            i = 0
            while i < len(self.rdns):
                if key == self.rdns[i].attr:
                    found = True
                    self.rdns[i] = new_rdn
                    if self.first_key_match: break
                i += 1
            if not found:
                raise KeyError("\"%s\" not found in %s" % (key, self.__str__()))
        else:
            raise TypeError("unsupported type for %s indexing, must be int, basestring or slice; not %s" % \
                                (self.__class__.__name__, key.__class__.__name__))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        return self.rdns == other.rdns

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("expected %s but got %s" % (self.__class__.__name__, other.__class__.__name__))

        result = cmp(len(self), len(other))
        if result != 0: return result
        i = 0
        while i < len(self):
            result = cmp(self[i], other[i])
            if result != 0: return result
            i += 1
        return 0

    def __add__(self, other):
        result = deepcopy(self)
        if isinstance(other, self.__class__):
            for rdn in other.rdns:
                result.rdns.append(deepcopy(rdn))
        elif isinstance(other, RDN):
                result.rdns.append(deepcopy(other))
        elif isinstance(other, basestring):
            dn = DN(other)
            for rdn in dn.rdns:
                result.rdns.append(deepcopy(rdn))
        else:
            raise TypeError("expected DN, RDN or basestring but got %s" % (other.__class__.__name__))

        return result

    def __iadd__(self, other):
        if isinstance(other, self.__class__):
            for rdn in other.rdns:
                self.rdns.append(deepcopy(rdn))
        elif isinstance(other, RDN):
                self.rdns.append(deepcopy(other))
        elif isinstance(other, basestring):
            dn = DN(other)
            self.__iadd__(dn)
        else:
            raise TypeError("expected DN, RDN or basestring but got %s" % (other.__class__.__name__))

        return self
