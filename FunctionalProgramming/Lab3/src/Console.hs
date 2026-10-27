{-# LANGUAGE CPP #-}
-- | Налаштування консолі на UTF-8, щоб кирилиця коректно виводилась у Windows
--   без ручного виклику `chcp 65001`.
module Console (setupConsole) where

import System.IO

#if defined(mingw32_HOST_OS)
import Foreign.C.Types (CInt (..), CUInt (..))

foreign import ccall unsafe "windows.h SetConsoleOutputCP"
  c_SetConsoleOutputCP :: CUInt -> IO CInt

foreign import ccall unsafe "windows.h SetConsoleCP"
  c_SetConsoleCP :: CUInt -> IO CInt
#endif

setupConsole :: IO ()
setupConsole = do
#if defined(mingw32_HOST_OS)
  _ <- c_SetConsoleOutputCP 65001
  _ <- c_SetConsoleCP 65001
#endif
  mapM_ (`hSetEncoding` utf8) [stdout, stdin, stderr]
