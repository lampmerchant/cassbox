# CassBox

Utility to create disk images which emulate the IBM PC 5150 cassette interface in DOSBox.


## Elevator Pitch

CassBox concatenates its own code together with an IBM PC BASIC ROM dump and, optionally, a cassette file to create a 320 KB (DS/DD, 8 sectors/track) diskette image which can be booted in DOSBox.  The code loads itself and the BASIC ROM dump into the top of the 640K conventional RAM space and installs a handler for the cassette interrupt which emulates the cassette interface.


## Caveats

CassBox is dependent on permissive behavior of INT 13 (specifically, the ability for disk reads to cross track boundaries) and accordingly may not work on real hardware.

CassBox assumes the target system has 640 KB of RAM and does not adjust for systems with less.

CassBox loads BASIC into RAM, not ROM.  While this is not known to cause any issues, it is possible for the BASIC ROM-in-RAM to become corrupted by an errant write.

Currently the only way to wind or rewind the tape is to use POKEs in BASIC.


## Technical Details

### CAS Format

The format of cassette files used by this program is the CAS format.  CAS files are simply the bytes that would be written to the cassette, including the leader of '1' bits (grouped into 0xFF bytes) followed by the sync '0' bit (represented as an 0xFE byte).  There is no way to represent silence in a CAS file, so one section is immediately followed by the next.


### Winding/Rewinding

The current position on the cassette is stored in four bytes:

```
97C0:0000 - Byte offset in block (low byte)
97C0:0001 - Byte offset in block (high byte)
97C0:0002 - Block number (low byte)
97C0:0003 - Block number (high byte)
```

Byte offset in block ranges from 0 to 511, block number ranges from 0 to 574.  When changing block number, byte offset MUST be set to 0 in order to ensure that the block is loaded from disk on the next cassette read.

Example (setting position to the beginning of block 259):

```
DEF SEG = &H97C0
POKE 0, 0
POKE 1, 0
POKE 2, 3  'Low byte of block number
POKE 3, 1  'High byte of block number, (256 * 1) + 3 = 259
```


### BASIC ROM Dumps

IBM PC BASIC is the copyrighted property of IBM and/or Microsoft and cannot be posted here.  For ease of use, if pointed to a MAME ROMs directory, CassBox will attempt to find and use the ROM dumps used by MAME.  Appropriate BASIC ROMs can be found associated with the `ibm5150` machine and possibly also others.

