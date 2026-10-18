// Marketing address box: remember the address and open the app.
import { useNavigate } from 'react-router';
import { saveDraftAddress, saveDraftPlace } from '../lib/session.ts';
import { AddressSearch } from './AddressSearch.tsx';

export function AddressForm({ cta }: { cta: string }) {
  const navigate = useNavigate();
  return (
    <AddressSearch
      cta={cta}
      onPlace={(place) => {
        saveDraftAddress(place.label);
        saveDraftPlace(place);
        navigate('/app');
      }}
      onText={(text) => {
        saveDraftAddress(text);
        saveDraftPlace(null);
        navigate('/app');
      }}
    />
  );
}
