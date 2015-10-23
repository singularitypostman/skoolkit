# -*- coding: utf-8 -*-

# Copyright 2012-2015 Richard Dymond (rjdymond@gmail.com)
#
# This file is part of SkoolKit.
#
# SkoolKit is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# SkoolKit is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# SkoolKit. If not, see <http://www.gnu.org/licenses/>.

import inspect
import re

from skoolkit import SkoolKitError, SkoolParsingError, get_int_param

DELIMITERS = {
    '(': ')',
    '[': ']',
    '{': '}'
}

INTEGER = '(\d+|\$[0-9a-fA-F]+)'

SIMPLE_PARAM = '([a-z]+=)?{}'.format(INTEGER)

PARAM = '([a-z]+=)?[-+]?{0}([-+*/]{0})*'.format(INTEGER)

ADDR_RANGE_PARAM = '({0}([+*/]{0})*|\([-+]?{0}([-+*/]{0})*\))'.format(INTEGER)

ADDR_RANGE = '{0}(-{0}){{,3}}(x{1})?'.format(ADDR_RANGE_PARAM, INTEGER)

def parse_ints(text, index=0, num=0, defaults=(), names=()):
    """Parse a string of comma-separated integer parameters. The string will be
    parsed until either the end is reached, or an invalid character is
    encountered. The set of valid characters consists of the comma, '$', the
    digits 0-9, and the letters A-F and a-f; if `names` is not empty, the set
    of valid characters also includes '=' and the letters g-z.

    :param text: The text to parse.
    :param index: The index at which to start parsing.
    :param num: The maximum number of parameters to parse; this is set to the
                number of elements in `names` if that list is not empty.
    :param defaults: The default values of the optional parameters.
    :param names: The names of the parameters; if not empty, keyword arguments
                  are parsed.
    :return: A list of the form ``[end, value1, value2...]``, where:

             * ``end`` is the index at which parsing terminated
             * ``value1``, ``value2`` etc. are the parameter values
    """
    if index < len(text) and text[index] == '(':
        return _parse_ints_in_brackets(text, index, num, defaults, names)
    if names:
        pattern = '{0}(,({0})?)*'.format(SIMPLE_PARAM)
    else:
        pattern = '{0}(,({0})?){{,{1}}}'.format(SIMPLE_PARAM, num - 1)
    match = re.match(pattern, text[index:])
    if match:
        params = match.group()
    else:
        params = ''
    return [index + len(params)] + get_params(params, num, defaults, names=names)

def _parse_ints_in_brackets(text, index, num, defaults, names):
    end = text.find(')', index + 1)
    if end < 0:
        raise MacroParsingError("No closing bracket: {}".format(text[index:]))
    params = text[index + 1:end]
    if re.match('({0}(,({0})?)*)?$'.format(PARAM), params):
        return [end + 1] + get_params(params, num, defaults, names=names)
    if len(defaults) == max(num, len(names)) > 0:
        return [index] + list(defaults)
    raise MacroParsingError("Invalid integer(s) in parameter string: ({})".format(params))

def parse_params(text, index, p_text=None, chars='', except_chars='', only_chars=''):
    """Parse a string of the form ``params[(p_text)]``. The parameter string
    ``params`` will be parsed until either the end is reached, or an invalid
    character is encountered. The default set of valid characters consists of
    '$', '#', the digits 0-9, and the letters A-Z and a-z.

    :param text: The text to parse.
    :param index: The index at which to start parsing.
    :param p_text: The default value to use for text found in parentheses.
    :param chars: Characters to consider valid in addition to those in the
                  default set.
    :param except_chars: If not empty, all characters except those in this
                         string are considered valid.
    :param only_chars: If not empty, only the characters in this string are
                       considered valid.
    :return: A 3-tuple of the form ``(end, params, p_text)``, where:

             * ``end`` is the index at which parsing terminated
             * ``params`` is the parameter string
             * ``p_text`` is the text found in parentheses (if any)
    """
    start = index
    if except_chars:
        while index < len(text) and text[index] not in except_chars:
            index += 1
    elif only_chars:
        while index < len(text) and text[index] in only_chars:
            index += 1
    else:
        valid_chars = '$#' + chars
        while index < len(text) and (text[index].isalnum() or text[index] in valid_chars):
            index += 1
    params = text[start:index]
    end = index
    if index < len(text) and text[index] == '(':
        p_index = index
        depth = 1
        end += 1
        while end < len(text) and depth > 0:
            if text[end] == ')':
                depth -= 1
            elif text[end] == '(':
                depth += 1
            end += 1
        if depth > 0:
            raise MacroParsingError('No closing bracket: {}'.format(text[p_index:]))
        p_text = text[index + 1:end - 1]
    return end, params, p_text

def parse_image_macro(text, index=0, defaults=(), names=(), fname=''):
    result = parse_ints(text, index, defaults=defaults, names=names)
    end, crop_rect = _parse_crop_spec(text, result[0])
    end, fname, frame, alt = _parse_image_fname(text, end, fname)
    return end, crop_rect, fname, frame, alt, result[1:]

def get_address_range(text, index):
    match = re.match(ADDR_RANGE, text[index:])
    if match:
        spec = match.group()
        return index + len(spec), spec
    return index, None

def parse_address_range(spec, width):
    num = 1
    addr = spec
    if 'x' in addr:
        addr, num = spec.split('x', 1)
        num = evaluate(num)

    elements = [evaluate(m.group()) for m in re.finditer(ADDR_RANGE_PARAM, addr)]
    if len(elements) < 2:
        elements.append(elements[0])
    if len(elements) < 3:
        elements.append(1)
    if len(elements) < 4:
        elements.append(elements[2] * width)

    address, end_address, h_step, v_step = elements
    addresses = []
    while address <= end_address:
        addresses.append(address)
        if len(addresses) % width:
            address += h_step
        else:
            address += v_step - (width - 1) * h_step

    return addresses * num

def _parse_crop_spec(text, index):
    defaults = (0, 0, None, None)
    if index < len(text) and text[index] == '{':
        param_names = ('x', 'y', 'width', 'height')
        end, x, y, width, height = parse_ints(text, index + 1, defaults=defaults, names=param_names)
        if end < len(text) and text[end] == '}':
            return end + 1, (x, y, width, height)
        raise MacroParsingError("No closing brace on cropping specification: {}".format(text[index:]))
    return index, defaults

def _parse_image_fname(text, index, fname=''):
    if index >= len(text) or text[index] != '(':
        return index, fname, None, None
    end = text.find(')', index)
    if end < 0:
        raise MacroParsingError('No closing bracket: {}'.format(text[index:]))
    p_text = text[index + 1:end]
    alt = frame = None
    if p_text:
        if '|' in p_text:
            p_text, alt = p_text.split('|', 1)
        if '*' in p_text:
            p_text, frame = p_text.split('*', 1)
        if p_text:
            fname = p_text
        elif frame:
            fname = ''
        if frame == '':
            frame = fname
    return end + 1, fname, frame, alt

def evaluate(param):
    try:
        return eval(re.sub('\$([0-9a-fA-F]+)', r'int("\1",16)', param).replace('/', '//'))
    except:
        return None

def get_params(param_string, num=0, defaults=(), ints=None, names=()):
    params = []
    named_params = {}
    index = 0
    has_named_param = False
    if names:
        num = len(names)
    if param_string:
        for p in param_string.split(','):
            if index < len(names):
                name = names[index]
            else:
                name = index
            if p and names:
                param_name, eq, value = p.partition('=')
                if not eq:
                    if has_named_param:
                        raise MacroParsingError("Non-keyword argument after keyword argument: '{}'".format(p))
                    value = param_name
                elif param_name in names:
                    name = param_name
                    index = names.index(name)
                    has_named_param = True
                else:
                    raise MacroParsingError("Unknown keyword argument: '{}'".format(p))
            else:
                value = p
            if value:
                param = evaluate(value)
                if param is None:
                    if ints is None or index in ints:
                        raise MacroParsingError("Cannot parse integer '{}' in parameter string: '{}'".format(value, param_string))
                    param = value
                if names and name:
                    named_params[name] = param
                else:
                    params.append(param)
            elif not names:
                params.append(None)
            index += 1

    req = num - len(defaults)
    if named_params:
        for i in range(req):
            req_name = names[i]
            if req_name not in named_params:
                raise MacroParsingError("Missing required argument '{}'".format(req_name))
    elif index < req:
        if params:
            raise MacroParsingError("Not enough parameters (expected {}): '{}'".format(req, param_string))
        raise MacroParsingError("No parameters (expected {})".format(req))
    if index > num > 0:
        raise MacroParsingError("Too many parameters (expected {}): '{}'".format(num, param_string))

    if names:
        for i in range(req, num):
            name = names[i]
            if name not in named_params:
                named_params[name] = defaults[i - req]
        return [named_params[name] for name in names]

    params += [None] * (num - len(params))
    for i in range(req, num):
        if params[i] is None:
            params[i] = defaults[i - req]
    return params

def get_text_param(text, index, split=False, error=None):
    if index >= len(text) or text[index].isspace():
        raise MacroParsingError(error or "No text parameter")
    sep = ','
    delim1 = text[index]
    delim2 = DELIMITERS.get(delim1, delim1)
    if split and delim1 == delim2 and index + 1 < len(text) and text[index + 1] == delim1:
        sep = delim1
        delim1 = delim2 = delim1 + delim1
    start = index + len(delim1)
    end = text.find(delim2, start)
    if end < start:
        raise MacroParsingError("No terminating delimiter: {}".format(text[index:]))
    args = text[start:end]
    if args and split:
        args = args.split(sep)
    return end + len(delim2), args

class UnsupportedMacroError(SkoolKitError):
    pass

class MacroParsingError(SkoolKitError):
    pass

def get_macros(writer):
    macros = {}
    prefix = 'expand_'
    for name, method in inspect.getmembers(writer, inspect.ismethod):
        search = re.search('{}[a-z]+'.format(prefix), name)
        if search and name == search.group():
            macros['#' + name[len(prefix):].upper()] = method
    return macros

def expand_macros(macros, text, cwd=None):
    if text.find('#') < 0:
        return text

    while 1:
        search = None
        for m in re.finditer('#FOR(?![A-Z])', text):
            search = m
        if not search:
            for m in re.finditer('#(MAP|PEEK)(?![A-Z])', text):
                search = m
            if not search:
                search = re.search('#[A-Z]+', text)
        if not search:
            break
        marker = search.group()
        if not marker in macros:
            raise SkoolParsingError('Found unknown macro: {}'.format(marker))
        repf = macros[marker]
        start, index = search.span()
        try:
            if cwd is None:
                end, rep = repf(text, index)
            else:
                end, rep = repf(text, index, cwd)
        except UnsupportedMacroError:
            raise SkoolParsingError('Found unsupported macro: {}'.format(marker))
        except MacroParsingError as e:
            raise SkoolParsingError('Error while parsing {} macro: {}'.format(marker, e.args[0]))
        text = text[:start] + rep + text[end:]

    return text

def parse_item_macro(text, index, macro, def_link_text):
    end, anchor, link_text = parse_params(text, index)
    if anchor and anchor[0] != '#':
        raise MacroParsingError("Malformed macro: {}{}".format(macro, text[index:end]))
    if anchor == '#':
        raise MacroParsingError("No item name: {}{}".format(macro, text[index:end]))
    if link_text is None:
        link_text = def_link_text
    return end, anchor[1:], link_text

def parse_bug(text, index):
    # #BUG[#name][(link text)]
    return parse_item_macro(text, index, '#BUG', 'bug')

def parse_call(text, index, writer, cwd=None):
    # #CALL:methodName(args)
    macro = '#CALL'
    if index >= len(text):
        raise MacroParsingError("No parameters")
    if text[index] != ':':
        raise MacroParsingError("Malformed macro: {}{}...".format(macro, text[index]))
    end, method_name, arg_string = parse_params(text, index + 1, chars='_')
    if not method_name:
        raise MacroParsingError("No method name")
    if not hasattr(writer, method_name):
        writer.warn("Unknown method name in {} macro: {}".format(macro, method_name))
        return end, ''
    method = getattr(writer, method_name)
    if not inspect.ismethod(method):
        raise MacroParsingError("Uncallable method name: {}".format(method_name))
    if arg_string is None:
        raise MacroParsingError("No argument list specified: {}{}".format(macro, text[index:end]))
    args = get_params(arg_string, ints=())
    if cwd is not None:
        args.insert(0, cwd)
    try:
        retval = method(*args)
    except Exception as e:
        raise MacroParsingError("Method call {} failed: {}".format(text[index + 1:end], e))
    if retval is None:
        retval = ''
    return end, retval

def parse_chr(text, index):
    # #CHRnum or #CHR(num)
    return parse_ints(text, index, 1)

def parse_d(text, index, entry_holder):
    # #Daddr
    end, addr = parse_ints(text, index, 1)
    entry = entry_holder.get_entry(addr)
    if not entry:
        raise MacroParsingError('Cannot determine description for non-existent entry at {}'.format(addr))
    if not entry.description:
        raise MacroParsingError('Entry at {} has no description'.format(addr))
    return end, entry.description

def parse_erefs(text, index, entry_holder):
    # #EREFSaddr
    end, address = parse_ints(text, index, 1)
    ereferrers = entry_holder.get_entry_point_refs(address)
    if not ereferrers:
        raise MacroParsingError('Entry point at {} has no referrers'.format(address))
    ereferrers.sort()
    rep = 'routine at '
    if len(ereferrers) > 1:
        rep = 'routines at '
        rep += ', '.join('#R{}'.format(addr) for addr in ereferrers[:-1])
        rep += ' and '
    addr = ereferrers[-1]
    rep += '#R{}'.format(addr)
    return end, rep

def parse_fact(text, index):
    # #FACT[#name][(link text)]
    return parse_item_macro(text, index, '#FACT', 'fact')

def parse_font(text, index):
    # #FONT[:(text)]addr[,chars,attr,scale][{x,y,width,height}][(fname)]
    if index < len(text) and text[index] == ':':
        index, message = get_text_param(text, index + 1)
        if not message:
            raise MacroParsingError("Empty message: {}".format(text[index - 2:index]))
    else:
        message = ''.join([chr(n) for n in range(32, 128)])
    names = ('addr', 'chars', 'attr', 'scale')
    defaults = (len(message), 56, 2)
    end, crop_rect, fname, frame, alt, params = parse_image_macro(text, index, defaults, names, 'font')
    params.insert(0, message)
    return end, crop_rect, fname, frame, alt, params

def parse_for(text, index):
    # #FORstart,stop[,step](var,string[,sep])
    end, start, stop, step = parse_ints(text, index, 3, (1,))
    end, args = get_text_param(text, end, True, 'No variable name: {}'.format(text[index:end]))
    if not args:
        raise MacroParsingError("No variable name: {}".format(text[index:end]))
    var, s, sep = (args + [''] * (3 - len(args)))[:3]
    return end, sep.join([s.replace(var, str(n)) for n in range(start, stop + 1, step)])

def parse_html(text, index):
    # #HTML(text)
    return get_text_param(text, index)

def parse_link(text, index):
    # #LINK:PageId[#name](link text)
    macro = '#LINK'
    if index >= len(text):
        raise MacroParsingError("No parameters")
    if text[index] != ':':
        raise MacroParsingError("Malformed macro: {}{}...".format(macro, text[index]))
    end, param_str, link_text = parse_params(text, index + 1, except_chars=' (')
    if not param_str:
        raise MacroParsingError("No page ID: {}{}".format(macro, text[index:end]))
    if link_text is None:
        raise MacroParsingError("No link text: {}{}".format(macro, text[index:end]))
    page_id, sep, anchor = param_str.partition('#')
    if sep:
        anchor = sep + anchor
    return end, page_id, anchor, link_text

def parse_map(text, index):
    # #MAPvalue(default,k1:v1[,k2:v2...])
    end, value = parse_ints(text, index, 1)
    end, args = get_text_param(text, end, True, "No mappings provided: {}".format(text[index:end]))
    if args:
        default = args.pop(0)
    else:
        default = ''
    m = {}
    if args:
        for pair in args:
            k, v = pair.split(':', 1)
            m[evaluate(k)] = v
    return end, m.get(value, default)

def parse_peek(text, index, snapshot):
    # #PEEKaddr or #PEEK(addr)
    end, addr = parse_ints(text, index, 1)
    return end, str(snapshot[addr & 65535])

def parse_poke(text, index):
    # #POKE[#name][(link text)]
    return parse_item_macro(text, index, '#POKE', 'poke')

def parse_pokes(text, index, snapshot):
    # #POKESaddr,byte[,length,step][;addr,byte[,length,step];...]
    defaults = (1, 1)
    max_params = 4
    end, addr, byte, length, step = parse_ints(text, index, max_params, defaults)
    snapshot[addr:addr + length * step:step] = [byte] * length
    while end < len(text) and text[end] == ';':
        end, addr, byte, length, step = parse_ints(text, end + 1, max_params, defaults)
        snapshot[addr:addr + length * step:step] = [byte] * length
    return end, ''

def parse_pops(text, index, writer):
    # #POPS
    try:
        writer.pop_snapshot()
    except SkoolKitError as e:
        raise MacroParsingError(e.args[0])
    return index, ''

def parse_pushs(text, index, writer):
    # #PUSHS[name]
    end = index
    while end < len(text) and (text[end].isalnum() or text[end] in '$#'):
        end += 1
    writer.push_snapshot(text[index:end])
    return end, ''

def parse_r(text, index):
    # #Raddr[@code][#anchor][(link text)]
    end, params, link_text = parse_params(text, index, chars='@')
    anchor = ''
    anchor_index = params.find('#')
    if anchor_index >= 0:
        anchor = params[anchor_index:]
        params = params[:anchor_index]
    code_id = ''
    code_id_index = params.find('@')
    if code_id_index >= 0:
        code_id = params[code_id_index + 1:]
        params = params[:code_id_index]
    addr_str = params
    if not addr_str:
        raise MacroParsingError("No address")
    try:
        address = get_int_param(addr_str)
    except ValueError:
        raise MacroParsingError("Invalid address: {}".format(addr_str))
    return end, addr_str, address, code_id, anchor, link_text

def parse_refs(text, index, entry_holder):
    # #REFSaddr[(prefix)]
    end, addr_str, prefix = parse_params(text, index, '')
    if not addr_str:
        raise MacroParsingError("No address")
    try:
        address = get_int_param(addr_str)
    except ValueError:
        raise MacroParsingError("Invalid address: {}".format(addr_str))
    entry = entry_holder.get_entry(address)
    if not entry:
        raise MacroParsingError('No entry at {}'.format(addr_str))
    referrers = [ref.address for ref in entry.referrers]
    if referrers:
        referrers.sort()
        rep = '{} routine at '.format(prefix).lstrip()
        if len(referrers) > 1:
            rep = '{} routines at '.format(prefix).lstrip()
            rep += ', '.join('#R{}'.format(addr) for addr in referrers[:-1])
            rep += ' and '
        addr = referrers[-1]
        rep += '#R{}'.format(addr)
    else:
        rep = 'Not used directly by any other routines'
    return end, rep

def parse_reg(text, index, lower):
    # #REGreg
    end = index
    while end < len(text) and text[end] in "abcdefhlirspxy'":
        end += 1
    reg = text[index:end]
    if not reg:
        raise MacroParsingError('Missing register argument')
    if len(reg) > 3:
        raise MacroParsingError('Bad register: "{}"'.format(reg))
    if lower:
        return end, reg.lower()
    return end, reg.upper()

def parse_scr(text, index):
    # #SCR[scale,x,y,w,h,df,af][{x,y,width,height}][(fname)]
    names = ('scale', 'x', 'y', 'w', 'h', 'df', 'af')
    defaults = (1, 0, 0, 32, 24, 16384, 22528)
    return parse_image_macro(text, index, defaults, names, 'scr')

def parse_space(text, index):
    # #SPACE[num] or #SPACE([num])
    if index < len(text) and text[index] == '(':
        end, _, num_str = parse_params(text, index)
        try:
            return end, get_int_param(num_str)
        except ValueError:
            raise MacroParsingError("Invalid integer: '{}'".format(num_str))
    return parse_ints(text, index, 1, (1,))

def parse_udg(text, index):
    # #UDGaddr[,attr,scale,step,inc,flip,rotate,mask][:addr[,step]][{x,y,width,height}][(fname)]
    names = ('addr', 'attr', 'scale', 'step', 'inc', 'flip', 'rotate', 'mask')
    defaults = (56, 4, 1, 0, 0, 0, 1)
    end, addr, attr, scale, step, inc, flip, rotate, mask = parse_ints(text, index, defaults=defaults, names=names)
    if end < len(text) and text[end] == ':':
        end, mask_addr, mask_step = parse_ints(text, end + 1, defaults=(step,), names=('addr', 'step'))
    else:
        mask_addr = mask_step = None
        mask = 0
    end, crop_rect = _parse_crop_spec(text, end)
    end, fname, frame, alt = _parse_image_fname(text, end)
    return end, crop_rect, fname, frame, alt, (addr, attr, scale, step, inc, flip, rotate, mask, mask_addr, mask_step)

def parse_udgarray(text, index, udg_class=None, snapshot=None):
    # #UDGARRAYwidth[,attr,scale,step,inc,flip,rotate,mask];addr[,attr,step,inc][:addr[,step]];...[{x,y,width,height}](fname)
    names = ('width', 'attr', 'scale', 'step', 'inc', 'flip', 'rotate', 'mask')
    defaults = (56, 2, 1, 0, 0, 0, 1)
    end, width, attr, scale, step, inc, flip, rotate, mask = parse_ints(text, index, defaults=defaults, names=names)
    udg_array = [[]]
    has_masks = False
    while end < len(text) and text[end] == ';':
        names = ('attr', 'step', 'inc')
        defaults = (attr, step, inc)
        end, udg_addr = get_address_range(text, end + 1)
        if udg_addr is None:
            raise MacroParsingError('Expected UDG address range specification: #UDGARRAY{}'.format(text[index:end]))
        if end < len(text) and text[end] == ',':
            end, udg_attr, udg_step, udg_inc = parse_ints(text, end + 1, defaults=defaults, names=names)
        else:
            udg_attr, udg_step, udg_inc = defaults
        udg_addresses = parse_address_range(udg_addr, width)
        mask_addresses = []
        if end < len(text) and text[end] == ':':
            end, mask_addr = get_address_range(text, end + 1)
            if mask_addr is None:
                raise MacroParsingError('Expected mask address range specification: #UDGARRAY{}'.format(text[index:end]))
            if end < len(text) and text[end] == ',':
                end, mask_step = parse_ints(text, end + 1, defaults=(udg_step,), names=('step',))
            else:
                mask_step = udg_step
            if mask:
                mask_addresses = parse_address_range(mask_addr, width)
        if udg_class:
            has_masks = has_masks or len(mask_addresses) > 0
            mask_addresses += [None] * (len(udg_addresses) - len(mask_addresses))
            for u, m in zip(udg_addresses, mask_addresses):
                udg_bytes = [(snapshot[u + n * udg_step] + udg_inc) % 256 for n in range(8)]
                udg = udg_class(udg_attr, udg_bytes)
                if m is not None and mask:
                    udg.mask = [snapshot[m + n * mask_step] for n in range(8)]
                if len(udg_array[-1]) == width:
                    udg_array.append([udg])
                else:
                    udg_array[-1].append(udg)
    if not has_masks:
        mask = 0
    end, crop_rect = _parse_crop_spec(text, end)
    end, fname, frame, alt = _parse_image_fname(text, end)
    return end, crop_rect, fname, frame, alt, (udg_array, scale, flip, rotate, mask)

def parse_udgarray_with_frames(text, index, frame_map=None):
    # #UDGARRAY*frame1[,delay];frame2[,delay];...(fname)
    params = []
    delay = 32 # 0.32s
    end = index
    while end == index or (end < len(text) and text[end] == ';'):
        end += 1
        match = re.match('[^\s,;(]+', text[end:])
        if match:
            frame_id = match.group()
            end += len(frame_id)
            if end < len(text) and text[end] == ',':
                end, delay = parse_ints(text, end + 1, names=('delay',))
            params.append((frame_id, delay))

    fname = None
    if end < len(text) and text[end] == '(':
        fname_end = text.find(')', end + 1)
        if fname_end < 0:
            raise MacroParsingError('No closing bracket: {}'.format(text[end:]))
        fname = text[end + 1:fname_end]
        end = fname_end + 1
    if not fname:
        raise MacroParsingError('Missing filename: #UDGARRAY{}'.format(text[index:end]))
    alt = None
    if '|' in fname:
        fname, alt = fname.split('|', 1)

    if not params:
        raise MacroParsingError("No frames specified: #UDGARRAY{}".format(text[index:end]))

    frames = []
    if frame_map is not None:
        for frame_id, delay in params:
            if frame_id not in frame_map:
                raise MacroParsingError('No such frame: "{}"'.format(frame_id))
            frame = frame_map[frame_id]
            frame.delay = delay
            frames.append(frame)

    return end, fname, alt, frames
