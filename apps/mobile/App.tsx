import { StatusBar } from 'expo-status-bar';
import React from 'react';

import { ChatScreen } from './src/ui/ChatScreen';

export default function App(): React.JSX.Element {
  return (
    <>
      <StatusBar style="light" />
      <ChatScreen />
    </>
  );
}
