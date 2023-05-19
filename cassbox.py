import argparse
import hashlib
import os
import sys


#TODO stop access to INT 13 so other software can't access the disk?
#TODO keystroke hook to wind/rewind the tape?


CASSBOX_ASM = (
  
  # Initialization
  
  '0100 FA                 CLI                      ', # Interrupts off while we set up the stack
  '0101 B8 C0 87           MOV  AX,87C0             ', # Set up stack to have all of seg 0x87C0, which will keep it out of our way
  '0104 8E D0              MOV  SS,AX               ', #  "
  '0106 31 E4              XOR  SP,SP               ', #  "
  '0108 FB                 STI                      ', # Safe to reenable interrupts now
  '0109 B8 C0 97           MOV  AX,97C0             ', # Set up ES to point to high RAM
  '010C 8E C0              MOV  ES,AX               ', #  "
  '010E 31 C9              XOR  CX,CX               ', # Load MBR into high RAM
  '0110 E8 48 00           CALL 015B                ', #  "
  '0113 31 DB              XOR  BX,BX               ', #  "
  '0115 B8 01 02           MOV  AX,0201             ', #  "
  '0118 CD 13              INT  13                  ', #  "
  '011A B9 01 00           MOV  CX,0001             ', # Skip a sector, then load BASIC into RAM
  '011D E8 3B 00           CALL 015B                ', #  "
  '0120 BB 00 04           MOV  BX,0400             ', #  "
  '0123 B8 40 02           MOV  AX,0240             ', #  "
  '0126 CD 13              INT  13                  ', #  "
  '0128 31 C0              XOR  AX,AX               ', # Point data segment to interrupt vector table
  '012A 8E D8              MOV  DS,AX               ', #  "
  '012C 26                 ES:                      ', # Zero out tape counter
  '012D A3 00 00           MOV  [0000],AX           ', #  "
  '0130 26                 ES:                      ', #  "
  '0131 A3 02 00           MOV  [0002],AX           ', #  "
  '0134 FA                 CLI                      ', # Interrupts off while we modify vector table
  '0135 8C C0              MOV  AX,ES               ', # Set up the interrupt vector for our INT 12 handler (return memory size)
  '0137 C7 06 48 00 4F 00  MOV  WORD PTR [0048],004F', #  "
  '013D A3 4A 00           MOV  [004A],AX           ', #  "
  '0140 C7 06 54 00 EA 00  MOV  WORD PTR [0054],00EA', # Set up the interrupt vector for our INT 15 handler (cassette operations)
  '0146 A3 56 00           MOV  [0056],AX           ', #  "
  '0149 FB                 STI                      ', # Safe to reenable interrupts now
  '014A EA 00 00 00 98     JMP  9800:0000           ', # Jump into BASIC
  
  # Interrupt handler for INT 12 (get memory size in KB)
  
  '014F FB                 STI                      ', # Reenable interrupts
  '0150 B8 5F 02           MOV  AX,025F             ', # Lie and say memory size is only 607 KB
  '0153 CF                 IRET                     ', #  "
  
  # Subprogram: set up registers for an INT 13 call on a 320 KB (DS, DD, 8 sec/tk) diskette
  # Pre: when entered at 015B, CX contains the linear block number; when entered at 0154, cassette block number is used instead
  # Post: CX and DX set up with parameters for an INT 13 call, AX trashed
  
  '0154 8B 0E 02 00        MOV  CX,[0002]           ', # Load cassette block number for conversion
  '0158 83 C1 41           ADD  CX,+41              ', # Offset by 65 blocks to include BASIC and CassBox before conversion
  '015B 81 F9 80 02        CMP  CX,0280             ', # If block is out of bounds, raise carry and return to caller
  '015F 7D 18              JGE  0179                ', #  "
  '0161 89 C8              MOV  AX,CX               ', # Copy block number into AX and DX
  '0163 89 CA              MOV  DX,CX               ', #  "
  '0165 B1 04              MOV  CL,04               ', # Dump the bottom three bits (sector number) off AX and move the fourth into
  '0167 D3 E8              SHR  AX,CL               ', #  LSB of DH (head number); we will mask off other bits later
  '0169 D0 D6              RCL  DH,1                ', #  "
  '016B 88 D1              MOV  CL,DL               ', # Copy the bottom three bits of block number (sector number) into CL and
  '016D 80 E1 07           AND  CL,07               ', #  increment because sectors are 1-based
  '0170 FE C1              INC  CL                  ', #  "
  '0172 81 E2 00 01        AND  DX,0100             ', # Set DL (drive number) to 0, mask extra bits off head number, clear carry
  '0176 88 C5              MOV  CH,AL               ', # Move bits 11-4 of block into CH (track num), tho' only 9-4 should be used
  '0178 C3                 RET                      ', # Done
  '0179 F9                 STC                      ', # Raise carry to signal error
  '017A C3                 RET                      ', # Done
  
  # Subprogram: load cassette block buffer from disk if offset is at the beginning of it
  # Pre: offset within cassette block buffer stored in [0000], block number stored in [0002]
  # Post: if offset is 0, cassette block buffer loaded with cassette block; if offset was out of bounds, carry raised, else lowered
  
  '017B F7 06 00 00 FF FF  TEST WORD PTR [0000],FFFF', # If the offset within the buffer is nonzero, we don't need to do anything
  '0181 75 19              JNZ  019C                ', #  "
  '0183 B8 01 02           MOV  AX,0201             ', # Prepare to read one sector to memory
  # fall through
  
  # Subprogram: perform an INT 13 call targeting the cassette block buffer
  # Pre: INT 13 operation (typically read/write sectors) in AX
  # Post: INT 13 operation performed; AX and carry are left at values set by INT 13
  
  '0186 53                 PUSH BX                  ', # Preserve registers that will be trashed
  '0187 51                 PUSH CX                  ', #  "
  '0188 52                 PUSH DX                  ', #  "
  '0189 06                 PUSH ES                  ', #  "
  '018A 50                 PUSH AX                  ', #  "
  '018B E8 C6 FF           CALL 0154                ', # Set up CX and DX for an INT 13 operation
  '018E 58                 POP  AX                  ', # Retrieve saved AX so we can use it
  '018F 72 07              JB   0198                ', # If block out of bounds, pass carry to caller
  '0191 0E                 PUSH CS                  ', # Point to buffer location in memory
  '0192 07                 POP  ES                  ', #  "
  '0193 BB 00 02           MOV  BX,0200             ', #  "
  '0196 CD 13              INT  13                  ', # Perform operation, pass AX and carry on
  '0198 07                 POP  ES                  ', # Restore trashed registers
  '0199 5A                 POP  DX                  ', #  "
  '019A 59                 POP  CX                  ', #  "
  '019B 5B                 POP  BX                  ', #  "
  '019C C3                 RET                      ', # Done
  
  # Subprogram: write a byte to emulated cassette
  # Pre: AL contains byte to be written
  # Post: AL written to buffer, offset incremented, carry set on error; if written at end of buffer, buffer written to disk, offset
  #  reset to 0, block number incremented (but not loaded from disk yet)
  
  '019D 50                 PUSH AX                  ', # If at the top of buffer, load from disk
  '019E E8 DA FF           CALL 017B                ', #  "
  '01A1 58                 POP  AX                  ', #  "
  '01A2 72 24              JB   01C8                ', # If there was an error, skip with carry set
  '01A4 57                 PUSH DI                  ', # Write the byte to the buffer
  '01A5 8B 3E 00 00        MOV  DI,[0000]           ', #  "
  '01A9 88 85 00 02        MOV  [DI+0200],AL        ', #  "
  '01AD 47                 INC  DI                  ', # If we're at the end of the buffer, write it to disk, because we know it's
  '01AE F7 C7 FF 01        TEST DI,01FF             ', #  changed, advance to the top of the next block, and preserve carry in case
  '01B2 75 0F              JNZ  01C3                ', #  the write errored; TEST ensures that carry flag is low to indicate no
  '01B4 50                 PUSH AX                  ', #  error
  '01B5 B8 01 03           MOV  AX,0301             ', #  "
  '01B8 E8 CB FF           CALL 0186                ', #  "
  '01BB 58                 POP  AX                  ', #  "
  '01BC BF 00 00           MOV  DI,0000             ', #  "
  '01BF FF 06 02 00        INC  WORD PTR [0002]     ', #  "
  '01C3 89 3E 00 00        MOV  [0000],DI           ', # Save changed offset in buffer
  '01C7 5F                 POP  DI                  ', #  "
  '01C8 C3                 RET                      ', # Done
  
  # Subprogram: read a byte from emulated cassette
  # Post: AL contains byte read from cassette, offset incremented, carry set on error; if read from end of buffer, offset reset to
  #  0 and block number incremented (but not loaded from disk yet)
  
  '01C9 E8 AF FF           CALL 017B                ', # If at the top of buffer, load from disk
  '01CC 72 1B              JB   01E9                ', # If there was an error, skip with carry set
  '01CE 57                 PUSH DI                  ', # Read the byte from the buffer
  '01CF 8B 3E 00 00        MOV  DI,[0000]           ', #  "
  '01D3 8A 85 00 02        MOV  AL,[DI+0200]        ', #  "
  '01D7 47                 INC  DI                  ', # If we're at the end of the buffer, advance to the top of the next sector;
  '01D8 F7 C7 FF 01        TEST DI,01FF             ', #  both TEST and XOR ensure that carry flag is low to indicate no error
  '01DC 75 06              JNZ  01E4                ', #  "
  '01DE 31 FF              XOR  DI,DI               ', #  "
  '01E0 FF 06 02 00        INC  WORD PTR [0002]     ', #  "
  '01E4 89 3E 00 00        MOV  [0000],DI           ', # Save changed offset in buffer
  '01E8 5F                 POP  DI                  ', #  "
  '01E9 C3                 RET                      ', # Done
  
  # Interrupt handler for INT 15 (cassette operations)
  
  '01EA FB                 STI                      ', # Reenable interrupts
  '01EB 1E                 PUSH DS                  ', # Save old DS
  '01EC 0E                 PUSH CS                  ', # DS must equal CS for cassette location variable access
  '01ED 1F                 POP  DS                  ', #  "
  '01EE 08 E4              OR   AH,AH               ', # If AH is 0, turn on motor, which we ignore (OR sets carry low so no error)
  '01F0 74 0F              JZ   0201                ', #  "
  '01F2 FE CC              DEC  AH                  ', # If AH is 1, turn off motor, which we ignore (DEC doesn't affect carry so
  '01F4 74 0B              JZ   0201                ', #  no error)
  '01F6 FE CC              DEC  AH                  ', # If AH is 2, read from cassette
  '01F8 74 0B              JZ   0205                ', #  "
  '01FA FE CC              DEC  AH                  ', # If AH is 3, write to cassette
  '01FC 74 38              JZ   0236                ', #  "
  '01FE B4 80              MOV  AH,80               ', # If AH is none of these, return 0x80 in AH and set carry to indicate an
  '0200 F9                 STC                      ', #  error
  '0201 1F                 POP  DS                  ', #  "
  '0202 CA 02 00           RETF 0002                ', # Return to caller, preserving flags
  '0205 55                 PUSH BP                  ', # Preserve the registers that we will trash
  '0206 57                 PUSH DI                  ', #  "
  '0207 56                 PUSH SI                  ', #  "
  '0208 89 CF              MOV  DI,CX               ', # Move CX into DI so we can use CX to loop
  '020A 31 D2              XOR  DX,DX               ', # Set/reset 0xFF counter to zero
  '020C E8 BA FF           CALL 01C9                ', # Get a byte from the cassette
  '020F 72 68              JB   0279                ', # If we errored, handle it
  '0211 3C FF              CMP  AL,FF               ', # If the byte we received is anything but 0xFF, reset to zero and try again
  '0213 75 F5              JNZ  020A                ', #  "
  '0215 FE C2              INC  DL                  ', # If it's 0xFF, increment the 0xFF counter
  '0217 80 FA 80           CMP  DL,80               ', # Loop until we get 128 consecutive 0xFFs
  '021A 75 F0              JNZ  020C                ', #  "
  '021C E8 AA FF           CALL 01C9                ', # Get a byte from the cassette
  '021F 72 58              JB   0279                ', # If we errored, handle it
  '0221 3C FE              CMP  AL,FE               ', # If the byte we got is an 0xFE, that's our sync bit, so jump ahead
  '0223 74 06              JZ   022B                ', #  "
  '0225 3C FF              CMP  AL,FF               ', # If the byte we got is another 0xFF, keep on waiting for our sync bit
  '0227 74 F3              JZ   021C                ', #  "
  '0229 EB DF              JMP  020A                ', # Other byte values mean starting over
  '022B E8 9B FF           CALL 01C9                ', # Get a byte from the cassette
  '022E 72 49              JB   0279                ', # If we errored, handle it
  '0230 3C 16              CMP  AL,16               ', # If the byte we got is 0x16, that's our sync byte, so jump ahead
  '0232 74 04              JZ   0238                ', #  "
  '0234 EB D4              JMP  020A                ', # Other byte values mean starting over
  '0236 EB 4A              JMP  0282                ', # (Write needs this because it's out of range)
  '0238 31 ED              XOR  BP,BP               ', # Use BP to count actual-read bytes
  '023A BA FF FF           MOV  DX,FFFF             ', # Initialize CRC register to 0xFFFF
  '023D BE 02 01           MOV  SI,0102             ', # Initialize counter to 258
  '0240 E8 86 FF           CALL 01C9                ', # Get a byte from the cassette
  '0243 72 34              JB   0279                ', # If we errored, handle it
  '0245 30 C6              XOR  DH,AL               ', # Factor it into the CRC
  '0247 B9 08 00           MOV  CX,0008             ', #  "
  '024A D1 E2              SHL  DX,1                ', #  "
  '024C 73 04              JNB  0252                ', #  "
  '024E 81 F2 21 10        XOR  DX,1021             ', #  "
  '0252 E2 F6              LOOP 024A                ', #  "
  '0254 83 FE 02           CMP  SI,+02              ', # If we're reading the CRC, don't write to the output buffer
  '0257 7E 0A              JLE  0263                ', #  "
  '0259 09 FF              OR   DI,DI               ', # If we've reached the end of the number of bytes requested to read, jump
  '025B 74 06              JZ   0263                ', #  ahead
  '025D 4F                 DEC  DI                  ', # Decrement the number of bytes requested
  '025E 45                 INC  BP                  ', # Increment the number of bytes read
  '025F 26                 ES:                      ', # Move the byte to the output buffer and advance the pointer
  '0260 88 07              MOV  [BX],AL             ', #  "
  '0262 43                 INC  BX                  ', #  "
  '0263 4E                 DEC  SI                  ', # Decrement the counter and loop until we've read an entire 256-byte block
  '0264 75 DA              JNZ  0240                ', #  "
  '0266 81 FA 0F 1D        CMP  DX,1D0F             ', # If the CRC is bad, handle it as an error
  '026A 75 11              JNZ  027D                ', #  "
  '026C 09 FF              OR   DI,DI               ', # If we have bytes left to read, read another block
  '026E 75 CA              JNZ  023A                ', #  "
  '0270 30 E4              XOR  AH,AH               ', # Clear carry and set AH to 0 to for no error
  '0272 89 EA              MOV  DX,BP               ', # Return total bytes read in DX
  '0274 5E                 POP  SI                  ', # Restore registers
  '0275 5F                 POP  DI                  ', #  "
  '0276 5D                 POP  BP                  ', #  "
  '0277 EB 88              JMP  0201                ', # Done
  '0279 B4 02              MOV  AH,02               ', # Return "bad tape signals" error code
  '027B EB 02              JMP  027F                ', #  "
  '027D B4 01              MOV  AH,01               ', # Return "CRC error" error code
  '027F F9                 STC                      ', # Set carry to indicate an error
  '0280 EB F0              JMP  0272                ', # Rejoin above
  '0282 55                 PUSH BP                  ', # Preserve the registers that we will trash
  '0283 57                 PUSH DI                  ', #  "
  '0284 56                 PUSH SI                  ', #  "
  '0285 89 D5              MOV  BP,DX               ', # Preserve DX, we'll write it back later
  '0287 89 CF              MOV  DI,CX               ', # Move CX into DI so we can use CX to loop
  '0289 B9 3E 01           MOV  CX,013E             ', # Write 318 0xFFs to cassette
  '028C B0 FF              MOV  AL,FF               ', #  "
  '028E E8 0C FF           CALL 019D                ', #  "
  '0291 72 E6              JB   0279                ', #  "
  '0293 E2 F9              LOOP 028E                ', #  "
  '0295 B0 FE              MOV  AL,FE               ', # Write sync bit to cassette
  '0297 E8 03 FF           CALL 019D                ', #  "
  '029A 72 DD              JB   0279                ', # If we errored, handle it
  '029C B0 16              MOV  AL,16               ', # Write sync byte to cassette
  '029E E8 FC FE           CALL 019D                ', #  "
  '02A1 72 D6              JB   0279                ', # If we errored, handle it
  '02A3 BA FF FF           MOV  DX,FFFF             ', # Initialize CRC
  '02A6 BE 00 01           MOV  SI,0100             ', # Cassette block is 256 bytes
  '02A9 09 FF              OR   DI,DI               ', # If we've written requested bytes, don't read more from buffer
  '02AB 74 05              JZ   02B2                ', #  "
  '02AD 26                 ES:                      ', # Pick up the next byte to read
  '02AE 8A 07              MOV  AL,[BX]             ', #  "
  '02B0 43                 INC  BX                  ', # Increment the buffer pointer
  '02B1 4F                 DEC  DI                  ', # Decrement the count of bytes to write
  '02B2 E8 E8 FE           CALL 019D                ', # Write byte to cassette
  '02B5 72 C2              JB   0279                ', # If we errored, handle it
  '02B7 30 C6              XOR  DH,AL               ', # Factor written byte into the CRC
  '02B9 B9 08 00           MOV  CX,0008             ', #  "
  '02BC D1 E2              SHL  DX,1                ', #  "
  '02BE 73 04              JNB  02C4                ', #  "
  '02C0 81 F2 21 10        XOR  DX,1021             ', #  "
  '02C4 E2 F6              LOOP 02BC                ', #  "
  '02C6 4E                 DEC  SI                  ', # Decrement bytes left in block
  '02C7 75 E0              JNZ  02A9                ', # Loop to send the next if any are left
  '02C9 F7 D2              NOT  DX                  ', # Ones' complement the CRC and write to cassette, upper byte first
  '02CB 88 F0              MOV  AL,DH               ', #  "
  '02CD E8 CD FE           CALL 019D                ', #  "
  '02D0 72 A7              JB   0279                ', #  "
  '02D2 88 D0              MOV  AL,DL               ', #  "
  '02D4 E8 C6 FE           CALL 019D                ', #  "
  '02D7 72 A0              JB   0279                ', #  "
  '02D9 09 FF              OR   DI,DI               ', # If bytes are left to write, loop to write another block
  '02DB 75 C6              JNZ  02A3                ', #  "
  '02DD B9 04 00           MOV  CX,0004             ', # Write trailer to cassette
  '02E0 B0 FF              MOV  AL,FF               ', #  "
  '02E2 E8 B8 FE           CALL 019D                ', #  "
  '02E5 72 92              JB   0279                ', #  "
  '02E7 E2 F9              LOOP 02E2                ', #  "
  '02E9 F7 06 00 00 FF FF  TEST WORD PTR [0000],FFFF', # Unless we already did it, write the current  sector to disk and, if
  '02EF 74 08              JZ   02F9                ', #  nothing goes wrong, return no error
  '02F1 B8 01 03           MOV  AX,0301             ', #  "
  '02F4 E8 A6 FE           CALL 019D                ', #  "
  '02F7 72 80              JB   0279                ', #  "
  '02F9 E9 74 FF           JMP  0270                ', #  "
  
  # Trailer
  
  '02FC 00 00              DB   00,00               ', # Free space
  '02FE 55 AA              DB   55,AA               ', # MBR signature
  
)
CASSBOX_BIN = bytes(int(i, 16) for i in ' '.join(line[5:22] for line in CASSBOX_ASM).split())

DISK_IMAGE_SIZE = 327680
BASIC_ROM_SIZE = 8192
BASIC_ROM_NUMBER_OF_CHIPS = 4
CASSETTE_SIZE = DISK_IMAGE_SIZE - (len(CASSBOX_BIN) + BASIC_ROM_SIZE * BASIC_ROM_NUMBER_OF_CHIPS)

BASIC10_SHA256_SUM = '2452b03b4b724b5b81e8cc367809c521144f5fe4e0425caee42ac71240b9b102'
BASIC11_SHA256_SUM = '3033d1a54c99d7e2aa1fc7c8c2e51a56ae1b61bf4e70e8aa580f43c43e37a63e'
BASIC_SHA256_SUMS = (BASIC10_SHA256_SUM, BASIC11_SHA256_SUM)

BASIC10_MAME_FILES = ('5700019.u29', '5700027.u30', '5700035.u31', '5700043.u32')
BASIC11_MAME_FILES = ('5000019.u29', '5000021.u30', '5000022.u31', '5000023.u32')
BASIC_MAME_FILE_SETS_AND_SHA256_SUMS = ((BASIC10_MAME_FILES, BASIC10_SHA256_SUM), (BASIC11_MAME_FILES, BASIC11_SHA256_SUM))


def read_basic_rom_file(filepath, number_of_chips=1):
  '''Read a BASIC ROM file and complain if it's the wrong size.'''
  with open(filepath, 'rb') as fp:
    data = fp.read(BASIC_ROM_SIZE * number_of_chips)
    if len(data) != BASIC_ROM_SIZE * number_of_chips:
      raise ValueError(f'{filepath} is {len(data)} bytes in length, expected {BASIC_ROM_SIZE * number_of_chips} instead')
    return data


def read_cassette_file(filepath):
  '''Read a cassette file and pad it to the correct size, complain if it's over.'''
  with open(filepath, 'rb') as fp:
    data = fp.read(CASSETTE_SIZE)
    if fp.read(1):
      raise ValueError(f'cassette file {filepath} is longer than the maximum size of {CASSETTE_SIZE} bytes')
  if len(data) < CASSETTE_SIZE:
    data = b''.join((data, bytes(CASSETTE_SIZE - len(data))))
  return data


def get_mame_basic_rom(directory):
  '''Walk a MAME directory and extract the latest correct concatenated BASIC ROM.'''
  basic_roms = {k: None for k in BASIC_MAME_FILE_SETS_AND_SHA256_SUMS}
  for path, _, files in os.walk(directory):
    for file_set, sha256sum in BASIC_MAME_FILE_SETS_AND_SHA256_SUMS:
      if all(os.path.exists(os.path.join(path, rom_file)) for rom_file in file_set):
        try:
          data = b''.join(read_basic_rom_file(os.path.join(path, rom_file)) for rom_file in file_set)
        except ValueError as e:
          continue
        if hashlib.sha256(data).hexdigest() == sha256sum: basic_roms[(file_set, sha256sum)] = data
        sys.stderr.write(f'found valid rom set {file_set} in {path}\n')
    if basic_roms[BASIC_MAME_FILE_SETS_AND_SHA256_SUMS[-1]] is not None: break
  try:
    rom_file_set_and_sha256_sum, rom_data = [(k, rom_data) for k, rom_data in basic_roms.items() if rom_data is not None][-1]
    rom_file_set, rom_sha256_sum = rom_file_set_and_sha256_sum
    sys.stderr.write(f'using rom set {rom_file_set}\n')
    return rom_data
  except IndexError:
    return None


def main(argv):
  parser = argparse.ArgumentParser(description='Assemble a bootable 320 KB diskette image for DOSBox from a cassette BASIC ROM'
                                               ' dump and, optionally, a cassette file.')
  source = parser.add_mutually_exclusive_group(required=True)
  source.add_argument('--rom', metavar='FILENAME.BIN', help='filename of a cassette BASIC ROM dump')
  source.add_argument('--mamedir', metavar='DIRECTORY', help='path to a MAME directory where ibm5150 ROMs can be found')
  parser.add_argument('--output', metavar='FILENAME.IMG', default='cassbox.img', help='filename for produced diskette image')
  parser.add_argument('--cassette', metavar='FILENAME.CAS', help='cassette file to package into diskette image')
  args = parser.parse_args(argv[1:])
  
  if args.mamedir:
    basic_rom = get_mame_basic_rom(args.mamedir)
    if basic_rom is None:
      sys.stderr.write(f"couldn't find a valid set of BASIC ROMs in {args.mamedir}\n")
      return 1
  else:
    try:
      basic_rom = read_basic_rom_file(args.rom, BASIC_ROM_NUMBER_OF_CHIPS)
    except ValueError as e:
      sys.stderr.write(f'{str(e)}\n')
      return 2
    if hashlib.sha256(basic_rom).hexdigest() not in BASIC_SHA256_SUMS:
      sys.stderr.write('warning, the ROM file is not a known BASIC ROM, proceeding anyway\n')
  
  if args.cassette:
    try:
      cassette_data = read_cassette_file(args.cassette)
    except ValueError as e:
      sys.stderr.write(f'{str(e)}\n')
      return 3
  else:
    cassette_data = bytes(CASSETTE_SIZE)
  
  with open(args.output, 'wb') as fp:
    fp.write(CASSBOX_BIN)
    fp.write(basic_rom)
    fp.write(cassette_data)


if __name__ == '__main__': sys.exit(main(sys.argv))
